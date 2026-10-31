#!/usr/bin/env python3
"""Build sim_bfs.c from sim.c by replacing main with a BFS state explorer."""
import re

src = open('/home/xiaoshabi/lessons/ctf/qwb/crp-11741_bc69f9111bd2916dbcfd027469492846/work/sim.c').read()
i = src.index('int main(')
head = src[:i]

nff = src.count('putchar(48 + f')
nsrl = src.count('= (uint16_t)(((s')

bfs = r'''
#define NFF %d
#define NSRL %d
static char stbuf[NFF + NSRL*16 + 2];
static void getstate(char* buf) {
  int p = 0;
%s
%s
  buf[p] = 0;
}
static void st_set(const char* buf) {
  int p = 0;
%s
%s
}

#define HBITS 25
#define HSIZE (1u<<HBITS)
static char** table;
static unsigned long hash_str(const char* s) {
  unsigned long h = 2166136261u;
  while (*s) { h ^= (unsigned char)*s++; h *= 16777619u; }
  return h & (HSIZE - 1);
}
static long table_count = 0;
static int seen(const char* s) {
  unsigned long h = hash_str(s);
  while (table[h]) {
    if (strcmp(table[h], s) == 0) return 1;
    h = (h + 1) & (HSIZE - 1);
  }
  return 0;
}
static void add(const char* s) {
  unsigned long h = hash_str(s);
  while (table[h]) h = (h + 1) & (HSIZE - 1);
  table[h] = strdup(s);
  table_count++;
}

int main_bfs(long maxstates) {
  table = calloc(HSIZE, sizeof(char*));
  char** queue = malloc(sizeof(char*) * (maxstates + 16));
  char** path = malloc(sizeof(char*) * (maxstates + 16));
  long qh = 0, qt = 0;
  getstate(stbuf);
  queue[qt] = strdup(stbuf); path[qt] = strdup(""); qt++;
  add(stbuf);
  while (qh < qt && table_count < maxstates) {
    st_set(queue[qh]);
    for (int d = 0; d < 2; d++) {
      din = d;
      tick();
      getstate(stbuf);
      if (!seen(stbuf)) {
        add(stbuf);
        queue[qt] = strdup(stbuf);
        long pl = strlen(path[qh]);
        path[qt] = malloc(pl + 2);
        memcpy(path[qt], path[qh], pl);
        path[qt][pl] = '0' + d;
        path[qt][pl+1] = 0;
        qt++;
      }
      st_set(queue[qh]);
    }
    qh++;
  }
  fprintf(stderr, "bfs states=%%ld queue=%%ld\n", table_count, qt);
  { FILE* fs = fopen("paths.txt", "w");
    for (long i = 0; i < qt; i++) fprintf(fs, "%%s %%s\n", path[i], queue[i]);
    fclose(fs); }
  fprintf(stderr, "bfs states=%%ld queue=%%ld\n", table_count, qt);
  { FILE* fs = fopen("states.txt", "w");
    for (long i = 0; i < qt; i++) fprintf(fs, "%%s\n", queue[i]);
    fclose(fs); }
  /* print transition table */
  char idx[HSIZE];
  memset(idx, 0xff, HSIZE);
  for (long i = 0; i < qt; i++) { unsigned long h = hash_str(queue[i]); while (strcmp(table[h], queue[i]) != 0) h = (h + 1) & (HSIZE - 1); idx[h] = (char)i; if (i > 200) break; }
  for (long i = 0; i < qt && i < 200; i++) {
    st_set(queue[i]);
    printf("S%%ld:", i);
    for (int d = 0; d < 2; d++) {
      din = d; tick();
      getstate(stbuf);
      /* find index */
      unsigned long h = hash_str(stbuf);
      long j = -1;
      while (table[h]) { if (strcmp(table[h], stbuf) == 0) { for (long k2 = 0; k2 < qt; k2++) if (strcmp(queue[k2], stbuf) == 0) { j = k2; break; } break; } h = (h + 1) & (HSIZE - 1); }
      printf(" d%%d->S%%ld(out%%d)", d, j, v1 & 1);
      st_set(queue[i]);
    }
    printf("\n");
  }
  return 0;
}

int main(int argc, char** argv) {
  if (argc > 2 && argv[2][0] == 'b') return main_bfs(atol(argv[3] ? argv[3] : "200000"));
  long n = atol(argv[1]);
  const char* prog = (argc > 2) ? argv[2] : "";
  long plen = strlen(prog);
  for (long k = 0; k < n; k++) {
    if (plen > 0) din = (k < plen) ? (uint8_t)(prog[k] == '1') : (uint8_t)(prog[plen-1] == '1');
    tick();
    putchar(48 + (v1 & 1));
  }
  putchar(10);
  return 0;
}
''' % (nff, nsrl,
       '\n'.join("  buf[p++] = '0' + f%d;" % i for i in range(nff)),
       '\n'.join("  for (int b = 0; b < 16; b++) buf[p++] = '0' + ((s%d >> b) & 1);" % i for i in range(nsrl)),
       '\n'.join("  f%d = buf[p++] - '0';" % i for i in range(nff)),
       '\n'.join("  { uint16_t v = 0; for (int b = 0; b < 16; b++) v |= (uint16_t)((buf[p++] - '0') << b); s%d = v; }" % i for i in range(nsrl)))

open('/home/xiaoshabi/lessons/ctf/qwb/crp-11741_bc69f9111bd2916dbcfd027469492846/work/sim_bfs.c', 'w').write(head + bfs)
print('wrote sim_bfs.c nff', nff, 'nsrl', nsrl)
