"""
WAV 파일 재생 모듈

Raspberry Pi OS의 현재 오디오 출력 설정을 따르도록
PipeWire의 pw-play를 우선 사용합니다.

pw-play를 찾지 못하는 환경에서는 aplay를 대신 사용합니다.
"""

from pathlib import Path
import shutil
import subprocess
from typing import List

import config


class AudioPlayerError(RuntimeError):
    """오디오 파일 또는 재생 오류."""


def _validate_wav(path: Path) -> None:
    if not path.exists():
        raise AudioPlayerError(f"WAV 파일을 찾을 수 없습니다: {path}")

    if not path.is_file():
        raise AudioPlayerError(f"파일 경로가 아닙니다: {path}")

    if path.suffix.lower() != ".wav":
        raise AudioPlayerError(f"WAV 파일만 사용하세요: {path}")


def _player_command(path: Path) -> List[str]:
    """
    Raspberry Pi OS 데스크톱의 기본 출력 장치를 따르는
    pw-play를 우선 사용합니다.
    """
    if shutil.which("pw-play"):
        return ["pw-play", str(path)]

    command = ["aplay", "-q"]

    if config.APLAY_DEVICE:
        command.extend(["-D", config.APLAY_DEVICE])

    command.append(str(path))

    return command


def play_wav_async(path: Path) -> subprocess.Popen:
    """WAV 재생을 시작하고 즉시 Popen 객체를 반환합니다."""
    _validate_wav(path)

    command = _player_command(path)

    print(f"[Audio] 실행: {' '.join(command)}")

    try:
        return subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )

    except FileNotFoundError as exc:
        raise AudioPlayerError(
            "오디오 재생 프로그램을 찾지 못했습니다."
        ) from exc


def wait_for_audio(process: subprocess.Popen) -> None:
    """비동기로 시작한 WAV 재생이 끝날 때까지 기다립니다."""
    _, stderr = process.communicate()

    if process.returncode != 0:
        raise AudioPlayerError(
            "WAV 재생에 실패했습니다. "
            f"종료 코드={process.returncode}, 오류={stderr.strip()}"
        )


def play_wav_blocking(path: Path) -> None:
    """WAV 파일을 재생하고 끝날 때까지 기다립니다."""
    process = play_wav_async(path)
    wait_for_audio(process)