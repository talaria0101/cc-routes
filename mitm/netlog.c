/* cc-routes net tap: LD_PRELOAD egress logger. No sockets bound, no CA.
 *
 * The sandbox denies INET bind(2), so a listen-socket MITM proxy cannot run
 * here. This shim lives inside the target process and logs, for every
 * connection attempt and every plaintext handshake it can see:
 *   - getaddrinfo() node/service   (DNS intent: real hostnames)
 *   - connect() ip:port            (real peer; via the egress proxy this is
 *                                   the proxy address, not the destination)
 *   - send()/write() scans         ("CONNECT host:port" proxy lines and TLS
 *                                   ClientHello SNI, both visible in clear)
 *
 * Host-level visibility, encrypted traffic included. Exact URL paths come
 * from hook.mjs (fetch tap); this shim covers every binary (node, bun,
 * npm children, git) and catches anything the JS hook misses.
 *
 * Build: gcc -shared -fPIC -O2 -o netlog.so netlog.c -ldl
 * Use:   CC_NETLOG=/path/run.net.log LD_PRELOAD=$PWD/netlog.so <cmd>
 * Log:   JSONL append, one open fd. Stack buffers only in the hot path;
 *        dlsym lookups are cached; reentrancy guarded.
 */
#define _GNU_SOURCE
#include <arpa/inet.h>
#include <dlfcn.h>
#include <netdb.h>
#include <netinet/in.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <unistd.h>
#include <fcntl.h>
#include <time.h>

static int log_fd = -1;
static int in_hook = 0;
static char comm_name[48] = "?";

static int (*real_connect)(int, const struct sockaddr *, socklen_t) = NULL;
static int (*real_getaddrinfo)(const char *, const char *,
                               const struct addrinfo *,
                               struct addrinfo **) = NULL;
static ssize_t (*real_send)(int, const void *, size_t, int) = NULL;
static ssize_t (*real_write)(int, const void *, size_t) = NULL;

static void setup(void) {
  const char *p = getenv("CC_NETLOG");
  if (p && p[0] && log_fd < 0) {
    log_fd = open(p, O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC, 0644);
  }
  const char *c0 = getenv("CC_NETLOG_COMM");
  if (c0 && c0[0]) {
    size_t n = strlen(c0);
    if (n > sizeof(comm_name) - 1) n = sizeof(comm_name) - 1;
    memcpy(comm_name, c0, n);
    comm_name[n] = 0;
  } else {
    FILE *f = fopen("/proc/self/comm", "r");
    if (f) {
      if (fgets(comm_name, sizeof(comm_name), f)) {
        size_t n = strlen(comm_name);
        while (n && (comm_name[n-1] == '\n' || comm_name[n-1] == ' ')) {
          comm_name[--n] = 0;
        }
      }
      fclose(f);
    }
  }
  if (!real_connect) real_connect = dlsym(RTLD_NEXT, "connect");
  if (!real_getaddrinfo) real_getaddrinfo = dlsym(RTLD_NEXT, "getaddrinfo");
  if (!real_send) real_send = dlsym(RTLD_NEXT, "send");
  if (!real_write) real_write = dlsym(RTLD_NEXT, "write");
}

__attribute__((constructor)) static void init(void) { setup(); }

static void emit(const char *kind, const char *detail) {
  if (log_fd < 0 || in_hook) return;
  in_hook = 1;
  char line[2300];
  struct timespec ts;
  clock_gettime(CLOCK_REALTIME, &ts);
  int n = snprintf(line, sizeof(line),
                   "{\"ts\":%lld,\"pid\":%d,\"comm\":\"%s\","
                   "\"ev\":\"%s\",\"d\":\"%s\"}\n",
                   (long long)ts.tv_sec, (int)getpid(), comm_name,
                   kind, detail ? detail : "");
  if (n > 0) {
    size_t w = (size_t)n < sizeof(line) ? (size_t)n : sizeof(line) - 1;
    ssize_t r = write(log_fd, line, w);
    (void)r;
  }
  in_hook = 0;
}

/* "host:port" (CONNECT lines) or bare host (SNI) -> log, sanitized to
 * [A-Za-z0-9.:_-], truncated. Anything else is dropped silently. */
static void emit_host(const char *kind, const char *s, size_t len) {
  char out[256];
  size_t j = 0;
  for (size_t i = 0; i < len && j < sizeof(out) - 1; i++) {
    char c = s[i];
    if (c == 0 || c == '\r' || c == '\n' || c == ' ' || c == '/') break;
    if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
        (c >= '0' && c <= '9') || c == '.' || c == '-' || c == '_' ||
        c == ':' || (j == 0 && c == '[') || c == ']') {
      out[j++] = c;
    } else {
      return;
    }
  }
  if (j < 4 || !memchr(out, '.', j)) return;
  out[j] = 0;
  emit(kind, out);
}

static void scan_buf(const char *b, size_t n) {
  /* CONNECT host:port (proxy request line) */
  if (n > 9 && memcmp(b, "CONNECT ", 8) == 0) {
    emit_host("connect_line", b + 8, n - 8);
  }
  /* TLS ClientHello SNI: walk extensions for server_name (type 0).
   * Best-effort parse; bails on any bounds violation. */
  if (n > 50 && (unsigned char)b[0] == 0x16 && (unsigned char)b[1] == 0x03) {
    size_t pos = 43; /* record(5) + hello fixed part up to session id len */
    if (pos >= n) return;
    size_t sid_len = (unsigned char)b[pos++];
    pos += sid_len;
    if (pos + 2 >= n) return;
    size_t cs_len = ((unsigned char)b[pos] << 8) | (unsigned char)b[pos+1];
    pos += 2 + cs_len;
    if (pos >= n) return;
    size_t cm_len = (unsigned char)b[pos++];
    pos += cm_len;
    if (pos + 2 >= n) return;
    size_t ext_total = ((unsigned char)b[pos] << 8) | (unsigned char)b[pos+1];
    pos += 2;
    size_t ext_end = pos + ext_total;
    if (ext_end > n) ext_end = n;
    while (pos + 4 <= ext_end) {
      unsigned et = ((unsigned char)b[pos] << 8) | (unsigned char)b[pos+1];
      unsigned el = ((unsigned char)b[pos+2] << 8) | (unsigned char)b[pos+3];
      pos += 4;
      if (pos + el > ext_end) return;
      if (et == 0 && el > 5) {
        /* server_name_list: list_len(2) name_type(1) name_len(2) name */
        size_t nl = ((unsigned char)b[pos+3] << 8) | (unsigned char)b[pos+4];
        if (nl && nl <= el && pos + 5 + nl <= ext_end &&
            b[pos+2] == 0) {
          emit_host("sni", b + pos + 5, nl);
          return;
        }
      }
      pos += el;
    }
  }
}

int getaddrinfo(const char *node, const char *service,
                const struct addrinfo *hints, struct addrinfo **res) {
  if (!real_getaddrinfo) setup();
  if (node && !in_hook) {
    char detail[300];
    snprintf(detail, sizeof(detail), "%s", node);
    emit("dns", detail);
  }
  return real_getaddrinfo(node, service, hints, res);
}

int connect(int fd, const struct sockaddr *addr, socklen_t len) {
  if (!real_connect) setup();
  if (!in_hook && addr) {
    char ip[INET6_ADDRSTRLEN] = "?";
    unsigned port = 0;
    if (addr->sa_family == AF_INET && len >= sizeof(struct sockaddr_in)) {
      const struct sockaddr_in *a = (const struct sockaddr_in *)addr;
      inet_ntop(AF_INET, &a->sin_addr, ip, sizeof(ip));
      port = ntohs(a->sin_port);
    } else if (addr->sa_family == AF_INET6 &&
               len >= sizeof(struct sockaddr_in6)) {
      const struct sockaddr_in6 *a = (const struct sockaddr_in6 *)addr;
      inet_ntop(AF_INET6, &a->sin6_addr, ip, sizeof(ip));
      port = ntohs(a->sin6_port);
    }
    if (ip[0] != '?') {
      char detail[80];
      snprintf(detail, sizeof(detail), "%s:%u", ip, port);
      emit("connect", detail);
    }
  }
  return real_connect(fd, addr, len);
}

ssize_t send(int fd, const void *buf, size_t n, int flags) {
  if (!real_send) setup();
  if (buf && n > 9 && !in_hook) scan_buf((const char *)buf, n);
  return real_send(fd, buf, n, flags);
}

ssize_t write(int fd, const void *buf, size_t n) {
  if (!real_write) setup();
  if (buf && n > 9 && !in_hook) scan_buf((const char *)buf, n);
  return real_write(fd, buf, n);
}
