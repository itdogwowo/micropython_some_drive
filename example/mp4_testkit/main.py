def main():
    from lib.bootstrap import build_bus

    bus = build_bus()

    if bool(bus.shared.get("pipeline_enabled", True)):
        import _thread
        from Core1_engine import task_loop as core1_loop

        _thread.start_new_thread(core1_loop, (bus,))
        while not bus.shared.get("core1_ready", False):
            pass

    from Core0_worker import task_loop as core0_loop

    core0_loop(bus)


if __name__ == "__main__":
    main()
