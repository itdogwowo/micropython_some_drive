import os


def init_sd(cfg):
    sd_cfg = cfg.get("SDcard", {}) or {}
    enabled = bool(sd_cfg.get("enable", 0))
    if not enabled:
        return None, "", None

    mount_point = (sd_cfg.get("phat", "/sd") or "/sd").rstrip("/")
    if not mount_point:
        mount_point = "/sd"

    try:
        os.stat(mount_point)
    except Exception:
        try:
            os.mkdir(mount_point)
        except Exception:
            pass

    try:
        import machine
    except Exception as e:
        return None, "", str(e)

    SDCard = getattr(machine, "SDCard", None)
    if SDCard is None:
        try:
            from machine import SDCard as _SDCard

            SDCard = _SDCard
        except Exception as e:
            return None, "", str(e)

    card_cfg = sd_cfg.get("config", {}) or {}
    gpio_cfg = sd_cfg.get("GPIO", {}) or {}

    try:
        sd = SDCard(
            slot=int(card_cfg.get("slot", 0)),
            width=int(card_cfg.get("width", 1)),
            sck=int(gpio_cfg.get("sck", 0)),
            cmd=int(gpio_cfg.get("cmd", 0)),
            data=gpio_cfg.get("data", None),
            freq=int(card_cfg.get("freq", 20_000_000)),
        )
        try:
            os.mount(sd, mount_point)
            return sd, mount_point, None
        except OSError as e:
            code = e.args[0] if getattr(e, "args", None) else None
            if code == 16 or "EBUSY" in str(e):
                return None, mount_point, None
            return None, "", str(e)
    except Exception as e:
        try:
            sd = SDCard(slot=int(card_cfg.get("slot", 0)))
            try:
                os.mount(sd, mount_point)
                return sd, mount_point, None
            except OSError as e2:
                code = e2.args[0] if getattr(e2, "args", None) else None
                if code == 16 or "EBUSY" in str(e2):
                    return None, mount_point, None
                return None, "", str(e2)
        except Exception:
            return None, "", str(e)
