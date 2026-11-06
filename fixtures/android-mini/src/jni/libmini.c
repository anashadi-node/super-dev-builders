
/* Pustaka native fixture — dipakai untuk memberi bukti ELF di dalam APK. */
const char *mini_sign(const char *payload) { return payload ? "signed" : "unsigned"; }
int mini_size(void) { return 32; }
