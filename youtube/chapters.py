
# Source: https://github.com/Jaydorah/youtube-local

'''Chapters of a video, read from the timestamps in its description:

    00:00 AI news intro
    01:03 Budget3D
    02:18 Reshoot 4D
'''
import re

from youtube import util

# Same rules as YouTube: the list starts at 0:00, has at least 3 timestamps,
# and they go up
MIN_CHAPTERS = 3

# 1:03, 01:03, 1:02:03, 90:15
TIME = r'\d{1,3}(?::\d\d){1,2}'
BULLETS = r'[\s\-–—•*·▶►➤>#]*'
SEPARATORS = r'[\s\-–—:|•·~>=.…]*'

# "01:03 Budget3D", "- [1:03] Budget3D", "2. 1:03 - Budget3D",
# "1:03 - 2:18 Budget3D"
TIME_FIRST_RE = re.compile(
    r'^' + BULLETS + r'(?:\d{1,3}[.)]\s+)?'
    r'[\[(]?(' + TIME + r')[\])]?'
    r'(?:\s*[-–—~]\s*[\[(]?' + TIME + r'[\])]?)?'   # end of the chapter
    r'(?=[\s\-–—:|]|$)'
    r'(.*)$'
)
# "Budget3D 01:03", "Budget3D - (1:03)"
TIME_LAST_RE = re.compile(
    r'^(.*?)(?<![\d:])[\[(]?(' + TIME + r')[\])]?\s*$'
)


def time_seconds(time_text):
    '''1:02:03 -> 3723. None if it isn't a real time, such as 1:75'''
    parts = [int(part) for part in time_text.split(':')]
    if parts[-1] >= 60 or (len(parts) == 3 and parts[1] >= 60):
        return None
    seconds = 0
    for part in parts:
        seconds = 60*seconds + part
    return seconds


def parse_line(line):
    '''(start in seconds, title) if the line is a timestamp with a title'''
    match = TIME_FIRST_RE.match(line)
    if match:
        time_text, title = match.groups()
    else:
        match = TIME_LAST_RE.match(line)
        if not match:
            return None
        title, time_text = match.groups()
    start = time_seconds(time_text)
    title = re.sub(r'^' + BULLETS, '', title)
    title = re.sub(r'^' + SEPARATORS + r'|' + SEPARATORS + r'$', '', title)
    # "Intro (" from "Intro (0:00)"
    title = re.sub(r'\s*[\[(]$', '', title)
    if start is None or not title:
        return None
    return start, title


def parse_chapters(description, duration=None):
    '''List of {'start': seconds, 'title', 'time_text'} in playing order.
    Empty if the description has no chapters.'''
    if not isinstance(description, str):
        return []
    lines = [parse_line(line) for line in description.splitlines()]
    lines = [line for line in lines if line is not None]

    for first, (start, _) in enumerate(lines):
        if start != 0:
            continue
        chapters = [lines[first]]
        for line in lines[first+1:]:
            # skips a timestamp that goes back, such as a typo or a
            # timestamp for something else further down
            if line[0] <= chapters[-1][0]:
                continue
            if duration and line[0] >= duration:
                continue
            chapters.append(line)
        if len(chapters) >= MIN_CHAPTERS:
            return [
                {
                    'start': start,
                    'title': title,
                    'time_text': util.seconds_to_timestamp(start),
                }
                for start, title in chapters
            ]
    return []
