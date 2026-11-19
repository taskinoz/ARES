"""Shared screenshot collection and frame review for the PC game harnesses.

Engine screenshots (the console ``screenshot <name>`` command) are preferred:
they read the rendered frame, need no focus change and can't capture other
windows. Desktop window grabs remain a labelled fallback. Every collected
frame is then reviewed: blank or black frames fail, and views that are nearly
identical to an earlier view are reported as warnings (the camera may not
have moved). Pillow is imported lazily; without it frames are not reviewed.
GPL-2.0-or-later.
"""
from __future__ import annotations

import re
import time
import uuid
from pathlib import Path

ENGINE_NAME = re.compile(r'ares_[a-f0-9]{32}_[0-9]+')
ENGINE_EXTENSIONS = ('.jpg', '.tga', '.png')
BLANK_STDDEV = 2.0     # 8-bit luminance; real scenes are far above this
BLACK_MEAN = 3.0
DUPLICATE_BITS = 8     # of 64 dHash bits; live scenes (foliage, effects) differ by a few
VIEW_INDEX = re.compile(r'view_?(\d+)\.png$')


def engine_name(index, token=None):
    """A unique, task-owned screenshot name the harness may later delete."""
    return f'ares_{token or uuid.uuid4().hex}_{int(index)}'


def collect_engine_screenshot(roots, name, path, since_ns):
    """Convert a fresh engine screenshot called ``name`` to PNG at ``path``.

    Only the exact task-owned file written at or after ``since_ns`` is used and
    then removed; other screenshots are never touched. Returns False while the
    file is missing or still being written.
    """
    if not ENGINE_NAME.fullmatch(name):
        raise ValueError('invalid engine screenshot name')
    from PIL import Image
    for root in roots:
        for extension in ENGINE_EXTENSIONS:
            source = Path(root) / (name + extension)
            if source.is_file() and not source.is_symlink() and source.stat().st_mtime_ns >= since_ns:
                try:
                    with Image.open(source) as frame:
                        frame.load()
                        Path(path).parent.mkdir(parents=True, exist_ok=True)
                        frame.convert('RGB').save(path, format='PNG')
                except (OSError, ValueError):
                    continue  # the engine may still be writing it
                source.unlink()
                return True
    return False


def wait_engine_screenshot(roots, name, path, since_ns, timeout=4.0, interval=0.25):
    end = time.monotonic() + timeout
    while True:
        if collect_engine_screenshot(roots, name, path, since_ns):
            return True
        if time.monotonic() >= end:
            return False
        time.sleep(interval)


def frame_stats(path):
    """Mean and spread of luminance plus a 64-bit difference hash."""
    from PIL import Image, ImageStat
    with Image.open(path) as image:
        gray = image.convert('L')
        stat = ImageStat.Stat(gray)
        small = gray.resize((9, 8))
    pixels = list(small.getdata())
    bits = 0
    for row in range(8):
        for column in range(8):
            bits = (bits << 1) | (pixels[row * 9 + column] > pixels[row * 9 + column + 1])
    return {'mean': round(stat.mean[0], 2), 'stddev': round(stat.stddev[0], 2), 'dhash': f'{bits:016x}'}


def frame_problems(stats):
    problems = []
    if stats['mean'] < BLACK_MEAN:
        problems.append('black frame')
    elif stats['stddev'] < BLANK_STDDEV:
        problems.append('blank frame (one colour)')
    return problems


def view_label(path, position):
    match = VIEW_INDEX.search(Path(path).name)
    return f'VIEW {match.group(1) if match else position}'


def review_frames(paths):
    """Review captured views. Returns frames, errors (blank/black) and warnings (near-duplicates)."""
    review = {'frames': [], 'errors': [], 'warnings': []}
    if not paths:
        return review
    try:
        import PIL  # noqa: F401
    except ImportError:
        review['warnings'].append('Pillow is not installed; frames were not reviewed')
        return review
    seen = []
    for position, path in enumerate(paths):
        label = view_label(path, position)
        try:
            stats = frame_stats(path)
        except (OSError, ValueError) as error:
            review['errors'].append(f'{label}: unreadable screenshot ({error})')
            continue
        problems = frame_problems(stats)
        review['errors'] += [f'{label}: {problem}' for problem in problems]
        if not problems:  # blank frames all hash alike; they already failed
            for other_label, other in seen:
                if bin(int(stats['dhash'], 16) ^ int(other, 16)).count('1') <= DUPLICATE_BITS:
                    review['warnings'].append(f'{label}: nearly identical to {other_label}; check the camera moved')
                    break
            seen.append((label, stats['dhash']))
        review['frames'].append({'path': Path(path).name, **stats, 'problems': problems})
    return review
