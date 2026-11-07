#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""QQ邮箱命令行工具：发送(带附件) / 查已发送 / 查收件箱 / 投递链路自测

凭据获取优先级: 命令行参数 > 环境变量(QQ_MAIL_ADDRESS / QQ_MAIL_AUTH_CODE) > 配置文件(~/.config/qq_mail/config.json)
配置文件格式: {"sender": "xxx@qq.com", "auth_code": "16位授权码"}
"""
import argparse
import imaplib
import json
import os
import smtplib
import sys
import time
from email.header import Header, decode_header
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate

SMTP_HOST, SMTP_PORT = 'smtp.qq.com', 465
IMAP_HOST, IMAP_PORT = 'imap.qq.com', 993
SENT_FOLDER = '"Sent Messages"'   # 带空格，SELECT时必须带引号

def dec(s):
    """解码MIME编码的中文头字段"""
    return ''.join(t.decode(c or 'utf-8') if isinstance(t, bytes) else t
                   for t, c in decode_header(s or ''))

def get_creds(args):
    sender = getattr(args, 'sender', None) or os.environ.get('QQ_MAIL_ADDRESS')
    code = getattr(args, 'auth_code', None) or os.environ.get('QQ_MAIL_AUTH_CODE')
    cfg = os.path.expanduser('~/.config/qq_mail/config.json')
    if (not sender or not code) and os.path.exists(cfg):
        with open(cfg, encoding='utf-8') as f:
            c = json.load(f)
        sender = sender or c.get('sender')
        code = code or c.get('auth_code')
    if not sender or not code:
        sys.exit('缺少凭据: 请用 --sender/--auth-code、环境变量 QQ_MAIL_ADDRESS/QQ_MAIL_AUTH_CODE，'
                 f'或创建配置文件 {cfg}')
    return sender, code

def build_msg(sender, to, subject, body, attachments=None, cc=None):
    msg = MIMEMultipart()
    msg['From'] = formataddr((Header('QQ邮箱', 'utf-8').encode(), sender))
    msg['To'] = formataddr((Header('', 'utf-8').encode(), to))
    if cc:
        msg['Cc'] = formataddr((Header('', 'utf-8').encode(), cc))
    msg['Subject'] = Header(subject, 'utf-8')
    msg['Date'] = formatdate(localtime=True)   # RFC 5322 要求，否则已发送列表无日期
    msg.attach(MIMEText(body, 'plain', 'utf-8'))
    for path in attachments or []:
        with open(path, 'rb') as f:
            part = MIMEApplication(f.read())
        # 中文附件名必须用Header编码，否则乱码
        part.add_header('Content-Disposition', 'attachment',
                        filename=Header(os.path.basename(path), 'utf-8').encode())
        msg.attach(part)
    return msg

def save_to_sent(sender, auth_code, msg):
    """关键: 原始SMTP发送不会写「已发送」副本，必须IMAP APPEND补一份"""
    M = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    M.login(sender, auth_code)
    M.append(SENT_FOLDER, '\\Seen', imaplib.Time2Internaldate(time.time()), msg.as_bytes())
    M.logout()

def cmd_send(args):
    sender, auth_code = get_creds(args)
    atts = args.attach or []
    for p in atts:
        if not os.path.exists(p):
            sys.exit(f'附件不存在: {p}')
    if args.dry_run:
        print(f'[演练] 将发送 {len(atts)} 个附件给 {args.to}:')
        for p in atts:
            print(f'  附件: {os.path.basename(p)} ({os.path.getsize(p)} 字节)')
        print(f'  主题: {args.subject}')
        return
    msg = build_msg(sender, args.to, args.subject, args.body, atts, args.cc)
    to_list = [args.to] + ([args.cc] if args.cc else [])
    for attempt in (1, 2, 3):
        try:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
                smtp.login(sender, auth_code)
                smtp.sendmail(sender, to_list, msg.as_string())
            save_to_sent(sender, auth_code, msg)
            print(f'✅ 已发送给 {args.to}（副本已存「已发送」）')
            return
        except Exception as e:
            print(f'第{attempt}次失败: {e}', file=sys.stderr)
            if attempt < 3:
                time.sleep(5)
    sys.exit('❌ 3次重试均失败')

def imap_connect(args):
    sender, auth_code = get_creds(args)
    M = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    M.login(sender, auth_code)
    return M, sender

def list_mailbox(args, folder):
    """注意: IMAP的SUBJECT中文搜索会崩溃(ascii编码错误)，必须SINCE+本地过滤"""
    M, sender = imap_connect(args)
    typ, _ = M.select(folder)
    since = time.strftime('%d-%b-%Y', time.localtime(time.time() - args.days * 86400))
    typ, msgs = M.search(None, 'SINCE', since)
    ids = msgs[0].split()
    rows = []
    for i in ids:
        typ, d = M.fetch(i, '(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM TO DATE)])')
        m = email.message_from_bytes(d[0][1])
        subj, frm = dec(m.get('Subject')), dec(m.get('From'))
        if args.contains and args.contains not in subj and args.contains not in frm:
            continue
        rows.append((m.get('Date', '?')[:22], frm[:28], subj[:60]))
    M.logout()
    return rows

def cmd_sent(args):
    rows = list_mailbox(args, SENT_FOLDER)
    print(f'最近{args.days}天「已发送」{len(rows)}封:')
    for date, frm, subj in reversed(rows):
        print(f'  [{date}] {subj}')

def cmd_inbox(args):
    rows = list_mailbox(args, '"INBOX"')
    print(f'最近{args.days}天「收件箱」{len(rows)}封:')
    for date, frm, subj in reversed(rows):
        print(f'  [{date}] {frm} | {subj}')

def cmd_selftest(args):
    """发一封自测邮件并验证到达收件箱，验证投递链路"""
    sender, auth_code = get_creds(args)
    subj = f'投递链路自测 {time.strftime("%H:%M:%S")}'
    msg = build_msg(sender, sender, subj, '自测邮件，收到即链路正常。', [])
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
        smtp.login(sender, auth_code)
        smtp.sendmail(sender, [sender], msg.as_string())
    print('自测邮件已发出，等待20秒...')
    time.sleep(args.wait)
    M, _ = imap_connect(args)
    M.select('"INBOX"')
    typ, msgs = M.search(None, 'SINCE', time.strftime('%d-%b-%Y'))
    found = False
    for i in msgs[0].split():
        typ, d = M.fetch(i, '(BODY.PEEK[HEADER.FIELDS (SUBJECT)])')
        if subj[:8] in dec(email.message_from_bytes(d[0][1]).get('Subject')):
            found = True
            break
    M.logout()
    print('✅ 自测邮件已到达收件箱，SMTP投递链路正常' if found else '❌ 未收到自测邮件，请检查垃圾箱/授权码')

import email  # noqa: E402  (供dec/list使用)

def main():
    def add_creds(sp):
        sp.add_argument('--sender', help='QQ邮箱地址')
        sp.add_argument('--auth-code', help='SMTP授权码(16位，非QQ密码)')
        return sp

    p = argparse.ArgumentParser(description='QQ邮箱工具')
    sub = p.add_subparsers(dest='cmd', required=True)

    sp = add_creds(sub.add_parser('send'))
    sp.add_argument('--to', required=True, help='收件人邮箱')
    sp.add_argument('--subject', required=True, help='主题(支持中文)')
    sp.add_argument('--body', default='', help='正文文本')
    sp.add_argument('--attach', nargs='*', default=[], help='附件路径(可多个)')
    sp.add_argument('--cc', help='抄送')
    sp.add_argument('--dry-run', action='store_true', help='演练，不真发')

    sp = add_creds(sub.add_parser('selftest'))
    sp.add_argument('--wait', type=int, default=20, help='等待秒数')

    for name in ('check-sent', 'check-inbox'):
        sp = add_creds(sub.add_parser(name))
        sp.add_argument('--days', type=int, default=2, help='查询最近几天')
        sp.add_argument('--contains', help='主题/发件人包含的关键字过滤')

    args = p.parse_args()
    {'send': cmd_send, 'selftest': cmd_selftest,
     'check-sent': cmd_sent, 'check-inbox': cmd_inbox}[args.cmd](args)

if __name__ == '__main__':
    main()
