# Enabled only by the camera profiles. Resolve before recipe parsing so PV,
# download names and sstate signatures all identify the selected release.
addhandler codex_latest_config
codex_latest_config[eventmask] = "bb.event.ConfigParsed"

python codex_latest_config() {
    from rpi5cam.codex_release import configure_latest
    configure_latest(d)
}
