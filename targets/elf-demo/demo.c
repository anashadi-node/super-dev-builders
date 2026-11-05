/* Biner uji untuk pipeline recon native (docs/RECON_NATIVE.md).
 *
 * Sumber ini ditambahkan 2026-11-05 karena biner `demo` sudah ter-commit
 * tanpa sumbernya. Kompilasi ulang TIDAK menghasilkan byte identik
 * (BuildID/nama path berbeda), jadi `demo` tetap disimpan apa adanya sebagai
 * artefak bukti; `demo.c` hanya memulihkan provenance: apa yang dibangun.
 *
 *   cc -O2 -fPIE -pie -o demo_rebuilt demo.c && ./demo_rebuilt
 *   -> elf-demo 42
 */
#include <stdio.h>

int main(void) {
    printf("elf-demo %d\n", 42);
    return 0;
}
