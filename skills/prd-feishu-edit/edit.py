#!/usr/bin/env python3
"""
prd-feishu-edit —— 对「已发布到飞书的 PRD」做外科手术式局部修改。

与 publish.py 的根本区别：
- publish.py = 清空整篇 + 从本地 HTML 重写 → 会抹掉用户在飞书里的手动改动。
- edit.py    = 以「飞书实时文档」为准，只替换用户指定的章节，其余逐块原样保留。

三个子命令：
  fetch  <飞书URL>
      读取实时文档，重建成 Markdown 打印出来（含各标题的 level / 根级序号），
      供 Claude 看清「当前真实内容」（包含用户手动改的部分）后决定改哪一节。

  review <plan.json>
      在原 PRD 的 wiki 节点下新建一个「修改建议」子节点，写入
      每个变更的「原内容 vs 修改后」对照，供用户评审。不动原文档。
      new_markdown 里的 {+新增+} 渲染成红色字体、{-删除-} 渲染成灰色划掉，
      一眼能看出这一节到底改了什么。成功后把 review_url 回写进 plan.json。

  apply  <plan.json>
      用户批准后调用：以实时文档为准，逐节定位标题锚点 → 删除该节旧块区间 →
      在原位插入新块（含原型图 PNG 上传绑定）。其余部分一律不动。
      默认把差异标记「落地」：新增文字转普通样式、被划掉的内容真正删除，
      原文档保持干净（plan 里加 "keep_diff_marks": true 可保留红字/划掉痕迹）。
      成功后在 review 子节点顶部加「已合并」横幅，差异对照保留作留痕。

plan.json 结构见本目录 SKILL.md。
"""
import copy, json, os, re, sys, time, subprocess, datetime
import urllib.parse as up
from pathlib import Path
import requests

# ---------------- 配置 ----------------
CONFIG = json.load(open(os.path.expanduser('~/.prd-feishu/config.json')))
APP_ID, APP_SECRET = CONFIG['app_id'], CONFIG['app_secret']
DOMAIN = CONFIG.get('app_domain', 'open.feishu.cn')
BASE = f'https://{DOMAIN}/open-apis'
CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

# 飞书 block_type 常量
BT_PAGE = 1
BT_TEXT = 2
BT_HEADING_BASE = 2      # heading{n} 的 block_type = BT_HEADING_BASE + n  (heading1=3 ... heading9=11)
BT_BULLET = 12
BT_ORDERED = 13
BT_CODE = 14
BT_QUOTE = 15
BT_TODO = 17
BT_DIVIDER = 22
BT_IMAGE = 27
BT_TABLE = 31
BT_TABLE_CELL = 32

HEADING_KEY = {3: 'heading1', 4: 'heading2', 5: 'heading3', 6: 'heading4',
               7: 'heading5', 8: 'heading6', 9: 'heading7', 10: 'heading8', 11: 'heading9'}

# ---------------- 差异标记 ----------------
# new_markdown 里用这两对标记表示改动：
#   {+新增的文字+}  → 渲染成红色字体
#   {-删除的文字-}  → 渲染成灰色 + 划掉
ADD_OPEN, ADD_CLOSE = '{+', '+}'
DEL_OPEN, DEL_CLOSE = '{-', '-}'
# 飞书 docx text_element_style.text_color 取值 1~7（1 红 / 2 橙 / 3 黄 / 4 绿 / 5 蓝 / 6 紫 / 7 灰）。
# 若你的租户里显示的颜色不是想要的，改 ~/.prd-feishu/config.json 的 diff_add_color / diff_del_color。
COLOR_ADD = int(CONFIG.get('diff_add_color', 1))
COLOR_DEL = int(CONFIG.get('diff_del_color', 7))
# 允许在 resolve 模式下整块删掉的块类型（正文/列表/引用/待办；标题不允许）
DROPPABLE = {BT_TEXT, BT_BULLET, BT_ORDERED, BT_QUOTE, BT_TODO}


def die(msg, code=1):
    print(msg)
    sys.exit(code)


def heading_level(block):
    """若是标题块返回其级别（1..9），否则返回 None。"""
    bt = block.get('block_type')
    if bt in HEADING_KEY:
        return bt - BT_HEADING_BASE
    return None


# ---------------- 飞书 token ----------------
def get_token():
    r = requests.post(f'{BASE}/auth/v3/tenant_access_token/internal',
                      json={'app_id': APP_ID, 'app_secret': APP_SECRET})
    d = r.json()
    if d.get('code') != 0:
        die(f'✗ 换取 token 失败: {d}')
    return d['tenant_access_token']


TOKEN = None
HEAD = None


def init_token():
    global TOKEN, HEAD
    TOKEN = get_token()
    HEAD = {'Authorization': f'Bearer {TOKEN}'}


# ---------------- URL / wiki 节点解析 ----------------
def resolve_url(url):
    """
    返回 dict: {url, url_type, url_token, doc_id, node(可能为None), host}
    node 仅在 wiki 类型时有（含 space_id / node_token / parent_node_token / title / obj_token）。
    """
    m = re.search(r'/(docx|wiki)/([A-Za-z0-9]+)', url)
    if not m:
        die(f'✗ 无法从 URL 解析 token: {url}')
    url_type, url_token = m.group(1), m.group(2)
    host = up.urlparse(url).netloc
    node = None
    if url_type == 'wiki':
        r = requests.get(f'{BASE}/wiki/v2/spaces/get_node', headers=HEAD,
                         params={'token': url_token})
        d = r.json()
        if d.get('code') != 0:
            die(f'✗ wiki get_node 失败: {d}')
        node = d['data']['node']
        if node.get('obj_type') != 'docx':
            die(f'✗ 节点不是 docx 类型: obj_type={node.get("obj_type")}')
        doc_id = node['obj_token']
    else:
        doc_id = url_token
    return {'url': url, 'url_type': url_type, 'url_token': url_token,
            'doc_id': doc_id, 'node': node, 'host': host}


# ---------------- 读取文档全部块 ----------------
def load_doc(doc_id):
    """返回 (id_map, root_block, root_children_blocks[按文档顺序])"""
    items = []
    page_token = ''
    while True:
        params = {'page_size': 500}
        if page_token:
            params['page_token'] = page_token
        r = requests.get(f'{BASE}/docx/v1/documents/{doc_id}/blocks',
                         headers=HEAD, params=params)
        d = r.json()
        if d.get('code') != 0:
            die(f'✗ 列 blocks 失败: {d}')
        items.extend(d['data']['items'])
        if d['data'].get('has_more'):
            page_token = d['data'].get('page_token', '')
            if not page_token:
                break
        else:
            break
    id_map = {b['block_id']: b for b in items}
    root = next((b for b in items if b['block_type'] == BT_PAGE), None)
    if root is None:
        die('✗ 找不到根块')
    # 用 root['children'] 保证文档顺序
    child_ids = root.get('children', [])
    root_children = [id_map[c] for c in child_ids if c in id_map]
    return id_map, root, root_children


# ---------------- 块 → Markdown 重建 ----------------
def elements_to_md(elements):
    out = []
    for e in elements or []:
        tr = e.get('text_run')
        if not tr:
            # mention / equation 等，尽量取 content
            for k in ('mention_doc', 'mention_user', 'equation'):
                if k in e:
                    out.append(e[k].get('content', '') or e[k].get('title', ''))
            continue
        content = tr.get('content', '')
        style = tr.get('text_element_style', {}) or {}
        if style.get('inline_code'):
            content = f'`{content}`'
        if style.get('strikethrough'):
            content = f'~~{content}~~'
        if style.get('bold'):
            content = f'**{content}**'
        if style.get('italic'):
            content = f'*{content}*'
        link = (style.get('link') or {}).get('url')
        if link:
            content = f'[{content}]({up.unquote(link)})'
        out.append(content)
    return ''.join(out)


def cell_text(id_map, cell_block):
    parts = []
    for cid in cell_block.get('children', []):
        cb = id_map.get(cid)
        if not cb:
            continue
        key = None
        if cb['block_type'] == BT_TEXT:
            key = 'text'
        elif cb['block_type'] in HEADING_KEY:
            key = HEADING_KEY[cb['block_type']]
        if key:
            parts.append(elements_to_md(cb.get(key, {}).get('elements', [])))
    txt = ' '.join(p for p in parts if p)
    return re.sub(r'\s*\n\s*', '<br>', txt).replace('|', '\\|').strip()


def block_to_md(id_map, block, depth=0):
    """把单个块（含其子块）重建为 Markdown 文本。"""
    bt = block.get('block_type')
    lvl = heading_level(block)
    if lvl is not None:
        return '#' * lvl + ' ' + elements_to_md(block[HEADING_KEY[bt]].get('elements', []))
    if bt == BT_TEXT:
        return elements_to_md(block.get('text', {}).get('elements', []))
    if bt == BT_BULLET:
        line = '  ' * depth + '- ' + elements_to_md(block.get('bullet', {}).get('elements', []))
        subs = [block_to_md(id_map, id_map[c], depth + 1)
                for c in block.get('children', []) if c in id_map]
        return '\n'.join([line] + [s for s in subs if s])
    if bt == BT_ORDERED:
        line = '  ' * depth + '1. ' + elements_to_md(block.get('ordered', {}).get('elements', []))
        subs = [block_to_md(id_map, id_map[c], depth + 1)
                for c in block.get('children', []) if c in id_map]
        return '\n'.join([line] + [s for s in subs if s])
    if bt == BT_QUOTE:
        return '> ' + elements_to_md(block.get('quote', {}).get('elements', []))
    if bt == BT_CODE:
        code = elements_to_md(block.get('code', {}).get('elements', []))
        return f'```\n{code}\n```'
    if bt == BT_DIVIDER:
        return '---'
    if bt == BT_IMAGE:
        return '🖼 [原型图 — 见原文档对应位置]'
    if bt == BT_TABLE:
        prop = block.get('table', {}).get('property', {})
        cols = prop.get('column_size') or 1
        cell_ids = block.get('children', [])
        cells = [id_map[c] for c in cell_ids if c in id_map]
        rows = [cells[i:i + cols] for i in range(0, len(cells), cols)]
        if not rows:
            return ''
        lines = []
        header = rows[0]
        lines.append('| ' + ' | '.join(cell_text(id_map, c) for c in header) + ' |')
        lines.append('| ' + ' | '.join('---' for _ in header) + ' |')
        for row in rows[1:]:
            lines.append('| ' + ' | '.join(cell_text(id_map, c) for c in row) + ' |')
        return '\n'.join(lines)
    # 其它块类型忽略
    return ''


def render_range_md(id_map, blocks):
    parts = []
    for b in blocks:
        s = block_to_md(id_map, b)
        if s and s.strip():
            parts.append(s)
    return '\n\n'.join(parts)


# ---------------- 章节定位 ----------------
def find_section_range(root_children, heading_text, level):
    """
    在 root_children 里定位标题锚点，返回 (start_idx, end_idx)（左闭右开）。
    end = 下一个 level<=当前level 的标题块下标；没有则到末尾。
    找不到锚点返回 (None, None)；多处命中打印警告，取第一处。
    """
    def norm(s):
        return re.sub(r'\s+', '', s or '')

    target = norm(heading_text)
    hits = []
    for i, b in enumerate(root_children):
        lvl = heading_level(b)
        if lvl == level:
            txt = elements_to_md(b[HEADING_KEY[b['block_type']]].get('elements', []))
            # 去掉可能的 markdown 强调符号再比较
            plain = re.sub(r'[*`]', '', txt)
            if norm(plain) == target:
                hits.append(i)
    if not hits:
        return None, None
    if len(hits) > 1:
        print(f'  ⚠ 标题「{heading_text}」(H{level}) 命中 {len(hits)} 处，取第一处 idx={hits[0]}')
    start = hits[0]
    end = len(root_children)
    for j in range(start + 1, len(root_children)):
        lvl = heading_level(root_children[j])
        if lvl is not None and lvl <= level:
            end = j
            break
    return start, end


# ---------------- 原型图渲染 ----------------
def render_protos(proto_html_files, workdir):
    """渲染 proto html 列表为 PNG，返回 png 路径列表（顺序一致）。"""
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    png_paths = []
    for i, hf in enumerate(proto_html_files, 1):
        hf = Path(hf)
        if not hf.exists():
            die(f'✗ 原型图 HTML 不存在: {hf}')
        png = workdir / f'edit-proto-{i}.png'
        cmd = [CHROME, '--headless', '--disable-gpu', '--no-sandbox',
               '--hide-scrollbars', '--window-size=940,3000',
               '--default-background-color=ffffffff',
               f'--screenshot={png}', f'file://{hf.resolve()}']
        subprocess.run(cmd, capture_output=True, text=True, timeout=40)
        if not png.exists():
            die(f'✗ 原型图渲染失败: {hf}')
        try:
            from PIL import Image, ImageChops
            img = Image.open(png).convert('RGB')
            bg = Image.new('RGB', img.size, (255, 255, 255))
            bbox = ImageChops.difference(img, bg).getbbox()
            if bbox:
                _, _, _, bt = bbox
                bt = min(img.size[1], bt + 20)
                img.crop((0, 0, img.size[0], bt)).save(png)
        except ImportError:
            pass
        print(f'  ✓ 原型图 [{i}] {png.name}')
        png_paths.append(png)
    return png_paths


# ---------------- 差异标记处理 ----------------
def check_diff_markers(markdown, where=''):
    """转换前先做一次粗粒度配对检查，给出比 API 报错友好得多的提示。"""
    pairs = [(ADD_OPEN, ADD_CLOSE, '新增'), (DEL_OPEN, DEL_CLOSE, '删除')]
    for op, cl, name in pairs:
        if markdown.count(op) != markdown.count(cl):
            die(f'✗ {where}差异标记不配对：{name}标记 `{op}` 出现 {markdown.count(op)} 次，'
                f'`{cl}` 出现 {markdown.count(cl)} 次。每处改动必须写成 `{op}…{cl}`。')


def _scan_markers(content, state):
    """把一段纯文本按标记切成 [(文本, 'add'/'del'/None), ...]，并返回退出时的状态。"""
    parts, buf, i = [], '', 0

    def flush():
        nonlocal buf
        if buf:
            parts.append((buf, state))
            buf = ''

    while i < len(content):
        two = content[i:i + 2]
        if state is None and two == ADD_OPEN:
            flush(); state = 'add'; i += 2
        elif state is None and two == DEL_OPEN:
            flush(); state = 'del'; i += 2
        elif state == 'add' and two == ADD_CLOSE:
            flush(); state = None; i += 2
        elif state == 'del' and two == DEL_CLOSE:
            flush(); state = None; i += 2
        else:
            buf += content[i]; i += 1
    flush()
    return parts, state


def _walk_blocks(blocks, first_level):
    """按文档顺序遍历 convert 返回的块树，返回 (有序块列表, id→块, 子→父)。"""
    id_map = {b['block_id']: b for b in blocks}
    ordered, parent_of, seen = [], {}, set()

    def walk(bid, parent):
        if bid in seen or bid not in id_map:
            return
        seen.add(bid)
        b = id_map[bid]
        parent_of[bid] = parent
        ordered.append(b)
        for c in b.get('children') or []:
            walk(c, b)

    for bid in first_level:
        walk(bid, None)
    for b in blocks:                      # 兜底：没被任何 children 引用到的块
        if b['block_id'] not in seen:
            seen.add(b['block_id'])
            ordered.append(b)
    return ordered, id_map, parent_of


def _text_container(block):
    """返回块里承载 elements 的那个子 dict（text / heading{n} / bullet / ordered / quote / todo …）。"""
    for v in block.values():
        if isinstance(v, dict) and isinstance(v.get('elements'), list):
            return v
    return None


def process_diff_marks(blocks, first_level, mode):
    """
    mode='mark'    —— 把 {+…+} 渲染成红字、{-…-} 渲染成灰色划掉（用于评审子节点）。
    mode='resolve' —— 落地成最终内容：新增文字保留为普通样式，被删文字整个丢弃（用于合并回原文档）。
    两种模式下标记符号本身都会从正文里消失。
    """
    ordered, id_map, parent_of = _walk_blocks(blocks, first_level)
    drop = set()
    for b in ordered:
        cont = _text_container(b)
        if cont is None:
            continue
        elems = cont.get('elements') or []
        had_text = any((e.get('text_run') or {}).get('content') for e in elems)
        state, new_elems = None, []
        for e in elems:
            tr = e.get('text_run')
            if not tr:
                new_elems.append(e)
                continue
            parts, state = _scan_markers(tr.get('content', ''), state)
            for text, st in parts:
                if mode == 'resolve' and st == 'del':
                    continue
                ne = copy.deepcopy(e)
                ne['text_run']['content'] = text
                if mode == 'mark' and st:
                    stl = ne['text_run'].setdefault('text_element_style', {})
                    if st == 'add':
                        stl['text_color'] = COLOR_ADD
                    else:
                        stl['strikethrough'] = True
                        stl['text_color'] = COLOR_DEL
                new_elems.append(ne)
        if state is not None:
            txt = ''.join((e.get('text_run') or {}).get('content', '') for e in elems)[:60]
            die(f'✗ 差异标记未闭合：「{txt}」。'
                f'`{ADD_OPEN}…{ADD_CLOSE}` / `{DEL_OPEN}…{DEL_CLOSE}` 必须在同一个段落 / 列表项 / '
                f'标题 / 表格单元格内成对闭合，不能跨行跨格。')

        now_empty = not any((e.get('text_run') or {}).get('content') for e in new_elems)
        if mode == 'resolve' and had_text and now_empty:
            if heading_level(b) is not None:
                die(f'✗ 不允许整条删除小节标题：请保留标题行本身，只删标题下的内容。')
            parent = parent_of.get(b['block_id'])
            in_cell = parent is not None and parent.get('block_type') == BT_TABLE_CELL
            if b.get('block_type') in DROPPABLE and not b.get('children') and not in_cell:
                drop.add(b['block_id'])       # 整行被划掉 → 合并时连空行一起去掉
                continue
        cont['elements'] = new_elems or [{'text_run': {'content': ''}}]

    if drop:
        blocks[:] = [b for b in blocks if b['block_id'] not in drop]
        first_level[:] = [i for i in first_level if i not in drop]
        for b in blocks:
            if b.get('children'):
                b['children'] = [c for c in b['children'] if c not in drop]
    return blocks, first_level


# ---------------- 插入 Markdown（含图片上传绑定）----------------
def insert_markdown(doc_id, markdown, index, png_paths, diff_mode='none'):
    """
    把一段 markdown 转 blocks 后插入到 doc_id 根块的 index 处。
    markdown 里的 ![](placeholder) 图片按出现顺序对应 png_paths。
    diff_mode: 'mark' 渲染差异标记 / 'resolve' 落地最终内容 / 'none' 原样。
    """
    r = requests.post(f'{BASE}/docx/v1/documents/blocks/convert',
                      headers={**HEAD, 'Content-Type': 'application/json'},
                      json={'content_type': 'markdown', 'content': markdown})
    d = r.json()
    if d.get('code') != 0:
        die(f'✗ markdown 转换失败: {d}')
    data = d['data']
    blocks = data['blocks']
    first_level = data['first_level_block_ids']
    if diff_mode in ('mark', 'resolve'):
        blocks, first_level = process_diff_marks(blocks, first_level, diff_mode)
    # 表格去 merge_info
    for b in blocks:
        if b.get('block_type') == BT_TABLE:
            prop = b.get('table', {}).get('property', {})
            prop.pop('merge_info', None)
    n_img = sum(1 for b in blocks if b.get('block_type') == BT_IMAGE)
    if n_img != len(png_paths):
        die(f'✗ 该段图片占位数({n_img}) 与提供的 PNG 数({len(png_paths)}) 不一致，检查 proto_html_files')

    r = requests.post(f'{BASE}/docx/v1/documents/{doc_id}/blocks/{doc_id}/descendant',
                      headers={**HEAD, 'Content-Type': 'application/json'},
                      json={'children_id': first_level, 'descendants': blocks, 'index': index})
    d = r.json()
    if d.get('code') != 0:
        die(f'✗ 插入块失败: {d}')
    inserted = d['data'].get('descendants', []) or d['data'].get('children', [])
    image_block_ids = [b['block_id'] for b in inserted if b.get('block_type') == BT_IMAGE]
    time.sleep(0.4)

    ok = 0
    for i, (bid, p) in enumerate(zip(image_block_ids, png_paths), 1):
        p = Path(p)
        with open(p, 'rb') as f:
            files = {
                'file_name': (None, p.name),
                'parent_type': (None, 'docx_image'),
                'parent_node': (None, bid),
                'size': (None, str(p.stat().st_size)),
                'file': (p.name, f, 'image/png'),
            }
            r = requests.post(f'{BASE}/drive/v1/medias/upload_all', headers=HEAD, files=files)
        up_resp = r.json()
        if up_resp.get('code') != 0:
            print(f'  [{i}] ✗ 图片上传失败: {up_resp}')
            continue
        ft = up_resp['data']['file_token']
        r = requests.patch(f'{BASE}/docx/v1/documents/{doc_id}/blocks/{bid}',
                           headers={**HEAD, 'Content-Type': 'application/json'},
                           json={'replace_image': {'token': ft}})
        if r.json().get('code') == 0:
            ok += 1
        else:
            print(f'  [{i}] ✗ 绑定图片失败: {r.json()}')
        time.sleep(0.35)
    if png_paths:
        print(f'  ✓ 图片绑定 {ok}/{len(png_paths)}')
    return len(blocks)


def clear_doc(doc_id):
    """清空一个文档的所有根级 children（用于 review 节点写入前 / 合并后重写）。"""
    _, root, root_children = load_doc(doc_id)
    n = len(root_children)
    if n > 0:
        requests.delete(f'{BASE}/docx/v1/documents/{doc_id}/blocks/{doc_id}/children/batch_delete',
                        headers={**HEAD, 'Content-Type': 'application/json'},
                        json={'start_index': 0, 'end_index': n})
        time.sleep(0.3)


# ================= 子命令：fetch =================
def cmd_fetch(url):
    init_token()
    info = resolve_url(url)
    id_map, root, root_children = load_doc(info['doc_id'])

    # 打印重建后的 Markdown
    print('=' * 60)
    print('当前飞书文档实时内容（以此为准，含用户手动改动）：')
    print('=' * 60)
    print(render_range_md(id_map, root_children))

    # 打印标题索引（供 Claude 准确挑锚点）
    print('\n' + '=' * 60)
    print('标题索引（heading_text / level / 根级序号）：')
    print('=' * 60)
    sections = []
    for i, b in enumerate(root_children):
        lvl = heading_level(b)
        if lvl is not None:
            txt = re.sub(r'[*`]', '', elements_to_md(b[HEADING_KEY[b['block_type']]].get('elements', [])))
            sections.append({'idx': i, 'level': lvl, 'heading_text': txt.strip()})
    print(json.dumps({'target_url': url, 'doc_id': info['doc_id'],
                      'sections': sections}, ensure_ascii=False, indent=2))


# ================= 子命令：review =================
def cmd_review(plan_path):
    plan = json.load(open(plan_path))
    init_token()
    info = resolve_url(plan['target_url'])
    if info['url_type'] != 'wiki' or not info['node']:
        die('✗ review 模式要求原 PRD 是 wiki 节点（才能在其下建子节点）。'
            '若原文档是裸 docx，请直接用 apply（不走评审子节点），或先把文档转入知识库。')

    node = info['node']
    space_id = node['space_id']
    parent_node_token = node['node_token']
    orig_title = node.get('title', 'PRD')

    id_map, root, root_children = load_doc(info['doc_id'])

    # 组装 review 文档的 markdown + 收集图片
    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    work = Path(f'/tmp/prd-feishu-edit-{datetime.datetime.now().strftime("%Y%m%d-%H%M%S")}')
    md_parts = [
        f'> 🛠 本节点由 prd-feishu-edit 生成，供评审。原文档：[{orig_title}]({plan["target_url"]})',
        f'> 修改说明：{plan.get("change_summary", "（未填写）")}',
        f'> **图例：{ADD_OPEN}红色字体{ADD_CLOSE} = 本次新增；{DEL_OPEN}划掉的灰字{DEL_CLOSE} = 本次删除；'
        f'黑色正文 = 未改动（原样保留）。**',
        f'> 生成时间：{ts}。批准后运行 `apply` 合并回原文档：'
        f'红字会变成正式内容、划掉的内容会被真正删除，本节点保留作为改动留痕。',
    ]
    all_pngs = []
    for si, sec in enumerate(plan['sections'], 1):
        lvl = sec['heading_level']
        htext = sec['heading_text']
        start, end = find_section_range(root_children, htext, lvl)
        if start is None:
            die(f'✗ 变更{si}：在实时文档里找不到标题「{htext}」(H{lvl})。'
                f'请先跑 fetch 用当前真实标题文本。')
        orig_md = render_range_md(id_map, root_children[start:end])
        new_md = sec['new_markdown']
        check_diff_markers(new_md, where=f'变更{si}「{htext}」的 new_markdown ')
        md_parts.append(f'\n---\n\n## 变更 {si}：{htext}\n')
        md_parts.append('### ⬛ 原内容（改之前的实时文档）\n')
        md_parts.append(orig_md if orig_md.strip() else '_（原为空）_')
        md_parts.append('\n### 🟩 修改后（红字=新增，划掉=删除，黑字=未动）\n')
        md_parts.append(new_md)
        # 渲染该节的原型图（若有）
        protos = sec.get('proto_html_files', [])
        if protos:
            pngs = render_protos(protos, work)
            all_pngs.extend(pngs)

    review_md = '\n\n'.join(md_parts)

    # 建子节点
    review_title = f'【修改建议】{orig_title} · {ts}'
    r = requests.post(f'{BASE}/wiki/v2/spaces/{space_id}/nodes',
                      headers={**HEAD, 'Content-Type': 'application/json'},
                      json={'obj_type': 'docx', 'node_type': 'origin',
                            'parent_node_token': parent_node_token, 'title': review_title})
    d = r.json()
    if d.get('code') != 0:
        die(f'✗ 创建 review 子节点失败: {d}')
    rn = d['data']['node']
    review_doc_id = rn['obj_token']
    review_node_token = rn['node_token']
    review_url = f'https://{info["host"]}/wiki/{review_node_token}'
    print(f'  ✓ review 子节点已建：{review_url}')

    # 写入对照内容（差异标记 → 红字 / 划掉）
    clear_doc(review_doc_id)
    insert_markdown(review_doc_id, review_md, 0, all_pngs, diff_mode='mark')

    # 回写 plan
    plan['review_url'] = review_url
    plan['review_node_token'] = review_node_token
    plan['review_space_id'] = space_id
    json.dump(plan, open(plan_path, 'w'), ensure_ascii=False, indent=2)

    print('\n' + '=' * 60)
    print('✓ 评审子节点已生成，请打开检查：')
    print(f'  {review_url}')
    print('  确认无误后回复「同意合并」，我再执行 apply 合并到原文档。')
    print('=' * 60)


# ================= 子命令：apply =================
def cmd_apply(plan_path):
    plan = json.load(open(plan_path))
    init_token()
    info = resolve_url(plan['target_url'])
    doc_id = info['doc_id']

    work = Path(f'/tmp/prd-feishu-edit-apply-{datetime.datetime.now().strftime("%Y%m%d-%H%M%S")}')

    # 合并时默认「落地」差异标记：新增文字转普通样式、划掉的内容真正删除。
    # 若想让原文档也保留红字/划掉的改动痕迹，在 plan.json 里加 "keep_diff_marks": true。
    diff_mode = 'mark' if plan.get('keep_diff_marks') else 'resolve'
    print(f'差异标记处理方式：{"保留红字/划掉痕迹" if diff_mode == "mark" else "落地为最终内容（推荐）"}')

    # 逐节处理：每处理一节都重新 load_doc（因为块区间会随插入/删除变化）
    for si, sec in enumerate(plan['sections'], 1):
        lvl = sec['heading_level']
        htext = sec['heading_text']
        check_diff_markers(sec['new_markdown'], where=f'变更{si}「{htext}」的 new_markdown ')
        id_map, root, root_children = load_doc(doc_id)
        start, end = find_section_range(root_children, htext, lvl)
        if start is None:
            die(f'✗ 变更{si}：在实时文档里找不到标题「{htext}」(H{lvl})，已中止。'
                f'（其余变更未提交，可重新 fetch 后重试）')
        n_del = end - start
        print(f'\n[变更{si}] 「{htext}」(H{lvl})  替换根级块 [{start}, {end}) 共 {n_del} 块')

        # 先渲染该节原型图
        protos = sec.get('proto_html_files', [])
        pngs = render_protos(protos, work) if protos else []

        # 删除旧区间
        if n_del > 0:
            r = requests.delete(
                f'{BASE}/docx/v1/documents/{doc_id}/blocks/{doc_id}/children/batch_delete',
                headers={**HEAD, 'Content-Type': 'application/json'},
                json={'start_index': start, 'end_index': end})
            d = r.json()
            if d.get('code') != 0:
                die(f'✗ 删除旧块失败: {d}')
            time.sleep(0.4)

        # 在原位插入新块
        insert_markdown(doc_id, sec['new_markdown'], start, pngs, diff_mode=diff_mode)
        print(f'  ✓ 变更{si} 已合并')
        time.sleep(0.4)

    # 在 review 子节点顶部插入「已合并」横幅（保留下方的差异对照作为改动留痕）
    rn_token = plan.get('review_node_token')
    if rn_token:
        try:
            ri = resolve_url(plan['review_url'])
            review_doc_id = ri['doc_id']
            done_ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
            note = (f'# ✅ 本修改建议已于 {done_ts} 合并到原文档\n\n'
                    f'原文档：[{plan["target_url"]}]({plan["target_url"]})\n\n'
                    f'下方「原内容 / 修改后」对照原样保留，作为本次改动的留痕；'
                    f'不需要了可手动删除本节点。\n\n---')
            insert_markdown(review_doc_id, note, 0, [])
            try:                                   # 顺手把节点标题标成已合并
                requests.post(
                    f'{BASE}/wiki/v2/spaces/{ri["node"]["space_id"]}/nodes/{rn_token}/update_title',
                    headers={**HEAD, 'Content-Type': 'application/json'},
                    json={'title': f'【已合并】{ri["node"].get("title", "修改建议")}'})
            except Exception:
                pass
            print('  ✓ review 子节点已标记为「已合并」（差异对照保留）')
        except SystemExit:
            print('  ⚠ review 子节点标记失败（不影响合并结果），可手动删除该节点')
        except Exception as e:
            print(f'  ⚠ review 子节点标记异常（不影响合并结果）: {e}')

    print('\n' + '=' * 60)
    print('✓ 已按批准的变更合并到原文档，其余部分原样保留：')
    print(f'  {plan["target_url"]}')
    print('=' * 60)


# ================= main =================
def main():
    if len(sys.argv) < 3:
        die(__doc__)
    cmd = sys.argv[1]
    if cmd == 'fetch':
        cmd_fetch(sys.argv[2])
    elif cmd == 'review':
        cmd_review(sys.argv[2])
    elif cmd == 'apply':
        cmd_apply(sys.argv[2])
    else:
        die(f'未知子命令: {cmd}（应为 fetch / review / apply）')


if __name__ == '__main__':
    main()
