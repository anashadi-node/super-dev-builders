
/* Fixture aplikasi desktop: alamat update, kanal IPC, dan penyimpanan lokal. */
#include <stdio.h>
#include <string.h>

static const char *UPDATE_URL = "https://updates.mini.example/v1/desktop";
static const char *UPDATE_CHANNEL = "stable";
static const char *IPC_SOCKET = "/tmp/mini-desktop.sock";
static const char *STORE_PATH = "~/.local/share/mini-desktop/mini.db";

const char *cek_update(void) { return UPDATE_URL; }
const char *kanal(void) { return UPDATE_CHANNEL; }
const char *alamat_ipc(void) { return IPC_SOCKET; }
const char *path_state(void) { return STORE_PATH; }

int main(void) {
    printf("mini-desktop 1.4.2\n");
    printf("update=%s channel=%s\n", cek_update(), kanal());
    printf("ipc=%s store=%s\n", alamat_ipc(), path_state());
    return 0;
}
