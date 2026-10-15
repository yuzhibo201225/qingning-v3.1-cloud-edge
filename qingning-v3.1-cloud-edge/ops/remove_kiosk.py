#!/usr/bin/env python3
from pathlib import Path
home=Path.home();xdg=home/'.config/autostart/pi-cafe-classroom.desktop'
if xdg.exists():xdg.unlink();print('已禁用 XDG 自启动')
lwc=home/'.config/labwc/autostart'
if lwc.exists():
    lines=lwc.read_text().splitlines()
    kept=[line for line in lines if '# pi-cafe-classroom' not in line]
    if len(kept)<len(lines):lwc.write_text('\n'.join(kept)+'\n');print('已禁用 labwc 自启动')
print('仅撤销本项目自启动项，未影响其他自动启动项。')
