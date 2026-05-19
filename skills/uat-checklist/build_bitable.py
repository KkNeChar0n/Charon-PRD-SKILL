#!/usr/bin/env python3
"""Build a Feishu Bitable (UAT checklist) under a PRD wiki node.

Usage: build_bitable.py <PRD_URL> <CHECKLIST_JSON_PATH>
"""
import json
import os
import re
import sys
import time
import requests


def main():
    if len(sys.argv) < 3:
        print(f'用法: {sys.argv[0]} <PRD_URL> <CHECKLIST_JSON_PATH>')
        sys.exit(1)

    PRD_URL = sys.argv[1]
    CHECKLIST_PATH = sys.argv[2]

    CFG = json.load(open(os.path.expanduser('~/.prd-feishu/config.json')))
    APP_ID = CFG['app_id']
    APP_SECRET = CFG['app_secret']
    DOMAIN = CFG.get('app_domain', 'open.feishu.cn')
    BASE = f'https://{DOMAIN}/open-apis'

    # 1. 换 token
    t = requests.post(
        f'{BASE}/auth/v3/tenant_access_token/internal',
        json={'app_id': APP_ID, 'app_secret': APP_SECRET},
        timeout=10,
    ).json()
    if t.get('code') != 0:
        sys.exit(f'换取 token 失败: {t}')
    TOKEN = t['tenant_access_token']
    H = {
        'Authorization': f'Bearer {TOKEN}',
        'Content-Type': 'application/json; charset=utf-8',
    }
    print(f'[飞书] ✓ token: {TOKEN[:12]}...')

    # 2. 解析 PRD URL
    m = re.search(r'/(docx|wiki)/([A-Za-z0-9]+)', PRD_URL)
    if not m:
        sys.exit(f'PRD URL 解析失败: {PRD_URL}')
    kind, tok = m.group(1), m.group(2)
    if kind != 'wiki':
        sys.exit('PRD URL 必须是 wiki 节点（/wiki/...），docx 直链没有父节点信息无法在其下建子节点')

    PRD_NODE_TOKEN = tok
    r = requests.get(
        f'{BASE}/wiki/v2/spaces/get_node',
        headers=H,
        params={'token': PRD_NODE_TOKEN},
        timeout=10,
    ).json()
    if r.get('code') != 0:
        sys.exit(f'PRD 节点查询失败: {r}')
    node = r['data']['node']
    SPACE_ID = node['space_id']
    PRD_DOC_ID = node['obj_token']
    PRD_TITLE = node.get('title', 'PRD')
    print(f'[飞书] PRD: 「{PRD_TITLE}」 space={SPACE_ID} docx={PRD_DOC_ID}')

    # 3. 加载 checklist JSON
    checklist = json.load(open(CHECKLIST_PATH))
    total_modules = len(checklist)
    total_items = sum(len(m.get('items', [])) for m in checklist)
    total_subs = sum(
        len(it.get('sub_items', []) or [{}])
        for m in checklist
        for it in m.get('items', [])
    )
    print(f'[Checklist] 模块 {total_modules} / 验收项 {total_items} / 子项 {total_subs}')

    # 4. 在 PRD 节点下创建 Bitable 子节点
    r = requests.post(
        f'{BASE}/wiki/v2/spaces/{SPACE_ID}/nodes',
        headers=H,
        json={
            'obj_type': 'bitable',
            'parent_node_token': PRD_NODE_TOKEN,
            'node_type': 'origin',
            'title': '验收清单',
        },
        timeout=15,
    ).json()
    if r.get('code') != 0:
        sys.exit(f'创建 Bitable wiki 节点失败: {r}')
    bit_node = r['data']['node']
    APP_TOKEN = bit_node['obj_token']
    BIT_NODE_TOKEN = bit_node['node_token']
    print(f'[飞书] ✓ Bitable wiki 节点: {BIT_NODE_TOKEN}')

    # 5. 拿默认 table_id
    time.sleep(0.4)  # bitable 初始化稍慢，避免立即拿不到 table
    r = requests.get(
        f'{BASE}/bitable/v1/apps/{APP_TOKEN}/tables',
        headers=H,
        timeout=10,
    ).json()
    if r.get('code') != 0 or not r['data']['items']:
        sys.exit(f'获取默认表失败: {r}')
    TABLE_ID = r['data']['items'][0]['table_id']
    print(f'[Bitable] 默认 table: {TABLE_ID}')

    # 6. 列出已有字段（飞书会默认建 4 个：Text/Single option/Date/Attachment）
    r = requests.get(
        f'{BASE}/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/fields',
        headers=H,
        timeout=10,
    ).json()
    existing = r['data']['items']
    first_field_id = existing[0]['field_id']
    print(f'[Bitable] 默认字段: {[f["field_name"] for f in existing]}')

    # 6b. 删除首字段之外的默认字段（首字段是主索引列不能删，只能改名）
    for f in existing[1:]:
        time.sleep(0.35)
        rd = requests.delete(
            f'{BASE}/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/fields/{f["field_id"]}',
            headers=H,
            timeout=10,
        ).json()
        if rd.get('code') != 0:
            print(f'  ⚠ 删除默认字段「{f["field_name"]}」失败（保留）: {rd}')
        else:
            print(f'  ✓ 删除默认字段「{f["field_name"]}」')

    # 7. 重命名首字段为「模块」
    r = requests.put(
        f'{BASE}/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/fields/{first_field_id}',
        headers=H,
        json={'field_name': '模块', 'type': 1},
        timeout=10,
    ).json()
    if r.get('code') != 0:
        print(f'  ⚠ 重命名首字段失败（继续）: {r}')

    # 8. 追加其余字段
    fields_to_add = [
        ('验收项', 1),
        ('子项', 1),
        ('期望表现', 1),
        ('测试环境', 7),
        ('灰度环境', 7),
        ('线上环境', 7),
        ('备注', 1),
    ]
    for fname, ftype in fields_to_add:
        time.sleep(0.35)
        r = requests.post(
            f'{BASE}/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/fields',
            headers=H,
            json={'field_name': fname, 'type': ftype},
            timeout=10,
        ).json()
        if r.get('code') != 0:
            print(f'  ⚠ 添加字段「{fname}」失败（跳过）: {r}')
        else:
            print(f'  ✓ 字段「{fname}」 type={ftype}')

    # 9. 组装行
    records = []
    for module in checklist:
        mname = module.get('module', '')
        items = module.get('items', []) or []
        for item in items:
            iname = item.get('item', '')
            subs = item.get('sub_items', []) or []
            if not subs:
                records.append({'fields': {
                    '模块': mname,
                    '验收项': iname,
                    '子项': '',
                    '期望表现': '',
                    '测试环境': False,
                    '灰度环境': False,
                    '线上环境': False,
                    '备注': '',
                }})
            else:
                for sub in subs:
                    records.append({'fields': {
                        '模块': mname,
                        '验收项': iname,
                        '子项': sub.get('sub', ''),
                        '期望表现': sub.get('expected', ''),
                        '测试环境': False,
                        '灰度环境': False,
                        '线上环境': False,
                        '备注': '',
                    }})

    print(f'[Bitable] 准备插入 {len(records)} 行')

    # 10. 批量插入（每批 500 条上限）
    inserted = 0
    for i in range(0, len(records), 500):
        chunk = records[i:i + 500]
        time.sleep(0.4)
        r = requests.post(
            f'{BASE}/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/records/batch_create',
            headers=H,
            json={'records': chunk},
            timeout=30,
        ).json()
        if r.get('code') != 0:
            print(f'  ⚠ 第 {i//500 + 1} 批插入失败: {r}')
        else:
            inserted += len(chunk)
            print(f'  ✓ 第 {i//500 + 1} 批 {len(chunk)} 行')

    print(f'[Bitable] ✓ 共插入 {inserted}/{len(records)} 行')

    # 11. 构造 Bitable URL（沿用 PRD URL 的 host）
    host_m = re.match(r'https://([^/]+)', PRD_URL)
    host = host_m.group(1) if host_m else f'{DOMAIN.replace("open.","").replace("feishu.cn","feishu.cn")}'
    BIT_URL = f'https://{host}/wiki/{BIT_NODE_TOKEN}'

    # 12. 在 PRD 末尾追加链接段落
    try:
        r = requests.get(
            f'{BASE}/docx/v1/documents/{PRD_DOC_ID}/blocks',
            headers=H,
            params={'page_size': 500},
            timeout=15,
        ).json()
        items = r['data']['items']
        root = next(b for b in items if b['block_type'] == 1)
        children_count = sum(
            1 for b in items if b.get('parent_id') == root['block_id']
        )
        append_payload = {
            'index': children_count,
            'children': [
                {
                    'block_type': 4,
                    'heading2': {
                        'elements': [
                            {'text_run': {'content': '验收清单'}}
                        ]
                    },
                },
                {
                    'block_type': 2,
                    'text': {
                        'elements': [
                            {'text_run': {'content': f'飞书多维表格：{BIT_URL}'}}
                        ]
                    },
                },
            ],
        }
        rr = requests.post(
            f'{BASE}/docx/v1/documents/{PRD_DOC_ID}/blocks/{PRD_DOC_ID}/children',
            headers=H,
            json=append_payload,
            timeout=15,
        ).json()
        if rr.get('code') == 0:
            print(f'[PRD] ✓ 已在 PRD 末尾追加验收清单链接')
        else:
            print(f'[PRD] ⚠ 追加链接失败（不影响 Bitable）: {rr}')
    except Exception as e:
        print(f'[PRD] ⚠ 追加链接异常（不影响 Bitable）: {e}')

    # 13. 输出
    print('\n' + '=' * 40)
    print('✓ 验收清单已生成')
    print(f'  PRD: 「{PRD_TITLE}」')
    print(f'  Bitable: {BIT_URL}')
    print(f'  共 {total_modules} 模块 / {total_items} 验收项 / {inserted} 子项')
    print('=' * 40)


if __name__ == '__main__':
    main()
