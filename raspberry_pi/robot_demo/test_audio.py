#!/usr/bin/env python3
"""두 WAV 파일과 AUX 스피커만 단독 시험합니다."""

import time

import config
from audio_player import play_wav_blocking


def main() -> None:
    print("[Audio test] 01_name_call.wav 재생")
    play_wav_blocking(config.AUDIO_NAME_CALL)

    time.sleep(0.5)

    print("[Audio test] 02_lets_play.wav 재생")
    play_wav_blocking(config.AUDIO_LETS_PLAY)

    print("[Audio test] 완료")


if __name__ == "__main__":
    main()
