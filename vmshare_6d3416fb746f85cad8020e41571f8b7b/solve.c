#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define M32 0xFFFFFFFFu
#define M16 0xFFFFu

static const uint16_t C[16] = {0x1357,0x2468,0x369c,0x48ad,0x5be1,0x6cf2,0x7d03,0x8e14,
                               0x9f25,0xa036,0xb147,0xc258,0xd369,0xe47a,0xf58b,0x069c};
static uint16_t S0[16];

static inline uint16_t rotl16(uint16_t x,int k){return (uint16_t)(((x<<k)|(x>>(16-k)))&M16);}
static inline uint16_t rotr16(uint16_t x,int k){return (uint16_t)(((x>>k)|(x<<(16-k)))&M16);}

static void prng(uint32_t val,uint32_t seed,uint16_t *out){
    uint32_t s=((val&0xFFFFFFu)^seed)&M32;
    s^=s>>13; s=(s*0x45d9f3bu)&M32; s^=s>>16;
    uint32_t acc=0;
    for(int i=0;i<8;i++){
        s=(s+acc+0x9E3779B9u)&M32;
        acc=(acc+0x7f4a7c15u)&M32;
        uint32_t t=s^(s>>13);
        t=(t*0x85ebca6bu)&M32;
        t=t^(t>>16);
        uint32_t u=t^(t>>16);
        out[i]=(uint16_t)(u&M16);
        s=t;
    }
}

static inline uint16_t rnd(uint16_t y,uint16_t w,uint16_t c){
    y^=y>>5;
    y=(uint16_t)((w+c+rotl16(y,3))&M16);
    y^=y>>7;
    return rotl16(y,9);
}
static inline uint16_t inv_xor_shr(uint16_t y,int k){
    uint16_t x=y; x=(uint16_t)(y^(x>>k)); x=(uint16_t)(y^(x>>k)); x=(uint16_t)(y^(x>>k));
    return x;
}
static inline uint16_t rnd_inv(uint16_t y,uint16_t w,uint16_t c){
    y=rotr16(y,9);
    y=inv_xor_shr(y,7);
    y=rotr16((uint16_t)((y-w-c)&M16),3);
    return inv_xor_shr(y,5);
}

typedef struct { uint32_t key; uint32_t x; } Ent;
static int cmp_ent(const void*a,const void*b){
    uint32_t ka=((const Ent*)a)->key, kb=((const Ent*)b)->key;
    return (ka<kb)?-1:((ka>kb)?1:0);
}

static uint16_t OUT[16];

int main(void){
    const char *iv="SIMD_TINY_BLOCK_IS_A_NIGHTMARE!!";
    for(int j=0;j<16;j++) S0[j]=(uint16_t)((unsigned char)iv[2*j] | (((unsigned char)iv[2*j+1])<<8));

    unsigned char buf[32];
    FILE *f=fopen("cipher.bin","rb");
    if(!f){printf("cannot open cipher.bin\n");return 1;}
    if(fread(buf,1,32,f)!=32){printf("short read\n");return 1;}
    fclose(f);
    for(int j=0;j<16;j++) OUT[j]=(uint16_t)(buf[2*j]|(buf[2*j+1]<<8));

    const uint32_t N=1u<<24;
    Ent *tab=(Ent*)malloc(sizeof(Ent)*N);
    if(!tab){printf("oom\n");return 1;}

    /* pass 1: forward over X */
    uint16_t b1[8];
    for(uint32_t x=0;x<N;x++){
        prng(x,0x31415926u,b1);
        uint16_t y0=S0[0], y1=S0[1];
        for(int i=0;i<8;i++){ y0=rnd(y0,b1[i],C[0]); y1=rnd(y1,b1[i],C[1]); }
        tab[x].key=((uint32_t)y0)|(((uint32_t)y1)<<16);
        tab[x].x=x;
    }
    fprintf(stderr,"pass1 done, sorting...\n");
    qsort(tab,N,sizeof(Ent),cmp_ent);

    /* pass 2: backward over Y */
    uint16_t b2[8];
    uint64_t checked=0;
    for(uint32_t y=0;y<N;y++){
        prng(y,0x27182818u,b2);
        uint16_t y0=OUT[0], y1=OUT[1];
        for(int i=7;i>=0;i--){ y0=rnd_inv(y0,b2[i],C[0]); y1=rnd_inv(y1,b2[i],C[1]); }
        uint32_t key=((uint32_t)y0)|(((uint32_t)y1)<<16);
        /* binary search */
        uint32_t lo=0, hi=N;
        while(lo<hi){ uint32_t mid=lo+((hi-lo)>>1); if(tab[mid].key<key) lo=mid+1; else hi=mid; }
        for(uint32_t p=lo;p<N && tab[p].key==key;p++){
            uint32_t x=tab[p].x;
            checked++;
            /* full verify */
            prng(x,0x31415926u,b1);
            uint16_t st[16];
            for(int j=0;j<16;j++) st[j]=S0[j];
            for(int i=0;i<8;i++) for(int j=0;j<16;j++) st[j]=rnd(st[j],b1[i],C[j]);
            for(int i=0;i<8;i++) for(int j=0;j<16;j++) st[j]=rnd(st[j],b2[i],C[j]);
            int ok=1;
            for(int j=0;j<16;j++) if(st[j]!=OUT[j]) {ok=0;break;}
            if(ok) printf("FOUND X24=%06X Y24=%06X  (x=%u y=%u)\n", x, y, x, y);
        }
    }
    fprintf(stderr,"candidates verified: %llu\n",(unsigned long long)checked);
    free(tab);
    return 0;
}
