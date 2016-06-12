import asyncio
import voice.worker


def run():
    loop = asyncio.get_event_loop()
    client = voice.worker.VoiceWorker(
        loop=loop,
        host='localhost',
        port=3000,
        client_id='1512',
        client_secret='hello_world'
    )

    try:
        loop.run_until_complete(client.start())
    except KeyboardInterrupt:
        client.stop_main_loop()

        pending = asyncio.Task.all_tasks()
        gathered = asyncio.gather(*pending)

        try:
            gathered.cancel()
            loop.run_until_complete(gathered)
            gathered.exception()

        except:
            pass

    finally:
        loop.close()


if __name__ == '__main__':
    run()
