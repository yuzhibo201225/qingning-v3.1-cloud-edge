#!/usr/bin/env python3
"""为外接显示器设置登录桌面后自动显示收银台；仅修改当前用户配置。"""
from pathlib import Path
import shutil, subprocess
root=Path(__file__).resolve().parents[1]
launcher=root/'ops/cashier_kiosk.sh'
launcher.chmod(0o755)
home=Path.home(); config=home/'.config'
# 优先检测实际运行的 labwc（Raspberry Pi OS Bookworm 常见）；其他桌面使用 XDG autostart
labwc=subprocess.run(['pgrep','-x','labwc'],capture_output=True).returncode==0 if shutil.which('pgrep') else False
if labwc:
    target=config/'labwc/autostart'
    target.parent.mkdir(parents=True,exist_ok=True)
    if not target.exists():
        system=Path('/etc/xdg/labwc/autostart')
        if system.is_file():shutil.copy2(system,target)
        else:target.write_text('# 用户自定义桌面启动项\n')
    old=target.read_text()
    line=f'/bin/bash "{launcher}" & # pi-cafe-classroom'
    if 'pi-cafe-classroom' not in old:target.write_text(old.rstrip('\n')+'\n'+line+'\n')
else:
    target=config/'autostart/pi-cafe-classroom.desktop';target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text('[Desktop Entry]\nType=Application\nName=Pi Cafe Classroom Cashier\nExec=/bin/bash '+str(launcher)+'\nTerminal=false\nX-GNOME-Autostart-enabled=true\n')
print('已设置桌面登录后启动收银台:',target)
print('注意：如果使用 Lite 系统或尚未进入图形桌面，外接屏幕无法显示网页。')
print('如已有自动启动浏览器，可能出现两个窗口；建议先在桌面手动测试。')
