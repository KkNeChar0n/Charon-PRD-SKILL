#!/usr/bin/env python3
"""Publish an existing PRD HTML file to Feishu Docs."""
import json, os, re, sys, time, html, subprocess, datetime, shutil
from pathlib import Path
import requests
from bs4 import BeautifulSoup, NavigableString, Tag

# ---------------- 配置与参数 ----------------
HTML_PATH = sys.argv[1] if len(sys.argv) > 1 else None
TARGET_URL = sys.argv[2] if len(sys.argv) > 2 else None
if not HTML_PATH or not os.path.exists(HTML_PATH):
    print(f'用法: {sys.argv[0]} <PRD html 路径> <飞书文档 URL>'); sys.exit(1)
if not TARGET_URL:
    print(f'用法: {sys.argv[0]} <PRD html 路径> <飞书文档 URL>'); sys.exit(1)

CONFIG = json.load(open(os.path.expanduser('~/.prd-feishu/config.json')))
APP_ID, APP_SECRET = CONFIG['app_id'], CONFIG['app_secret']
DOMAIN = CONFIG.get('app_domain', 'open.feishu.cn')
FOLDER = CONFIG.get('default_folder_token', '')
BASE = f'https://{DOMAIN}/open-apis'

WORK = Path(f'/tmp/prd-feishu-{datetime.datetime.now().strftime("%Y%m%d-%H%M%S")}')
WORK.mkdir(parents=True, exist_ok=True)
CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

print(f'工作目录: {WORK}')
print(f'输入文件: {HTML_PATH}')

# ---------------- 1. 解析 HTML ----------------
with open(HTML_PATH, 'r', encoding='utf-8') as f:
    raw = f.read()

soup = BeautifulSoup(raw, 'html.parser')

# 移除工具栏相关元素
for el in soup.select('#prd-toolbar, [data-prd-tool]'):
    el.decompose()

title_el = soup.find('h1')
PRD_TITLE = title_el.get_text(strip=True) if title_el else Path(HTML_PATH).stem

print(f'PRD 标题: {PRD_TITLE}')

body = soup.body or soup

# 提取「需求目标」全文：H2 文本含「需求目标」开始，到下一个 H2 之前的所有 <p> 内容
def extract_brief(body):
    parts = []
    found = False
    for el in body.find_all(['h1','h2','h3','p']):
        name = el.name
        if name == 'h2':
            if found:
                break
            txt = el.get_text(strip=True)
            if '需求目标' in txt:
                found = True
            continue
        if found and name == 'p':
            t = el.get_text(' ', strip=True)
            if t:
                parts.append(t)
    return ' '.join(parts).strip()

BRIEF = extract_brief(body)
print(f'需求目标摘要 ({len(BRIEF)} 字): {BRIEF[:60]}...')

# 判断一个 div 是不是「视觉原型图容器」：style 含 background:#f0f2f5 / #dbe9f4
def is_prototype_div(el):
    if el.name != 'div':
        return False
    style = (el.get('style') or '').replace(' ', '')
    return any(k in style for k in [
        'background:#f0f2f5',
        'background:#dbe9f4',
    ])

# 判断一个 div 是不是「产品架构图」（mindmap 容器）
def is_mindmap_div(el):
    if el.name != 'div':
        return False
    style = (el.get('style') or '').replace(' ', '')
    return 'background:#fafafa' in style and el.find('ul') is not None

# 收集原型图列表（顺序很重要）
proto_divs = []
for el in body.find_all(is_prototype_div):
    # 跳过嵌套的（只取最外层）
    if any(parent in [d for d in proto_divs] for parent in el.parents):
        continue
    proto_divs.append(el)

print(f'找到原型图块: {len(proto_divs)} 个')

# ---------------- 2. HTML → Markdown 转换 ----------------
def md_inline(node):
    """将 inline 节点（含 <b>, <span>, <code>, <a>, <s>, <br>）转为 Markdown 文本"""
    if isinstance(node, NavigableString):
        return str(node)
    if not isinstance(node, Tag):
        return ''
    if node.name == 'br':
        return '\n'
    inner = ''.join(md_inline(c) for c in node.children)
    if node.name in ('b', 'strong'):
        return f'**{inner.strip()}**'
    if node.name in ('i', 'em'):
        return f'*{inner.strip()}*'
    if node.name == 's':
        return f'~~{inner.strip()}~~'
    if node.name == 'code':
        return f'`{inner}`'
    if node.name == 'a':
        href = node.get('href', '')
        return f'[{inner}]({href})' if href else inner
    # 其他 inline 标签（span 等）直接取内容
    return inner

def md_table(table):
    """HTML table → Markdown table"""
    rows = []
    headers = []
    for tr in table.find_all('tr'):
        cells = tr.find_all(['th', 'td'])
        # 取 cell 文本（保留 <br> 为换行，再压缩到一行以兼容 Markdown 表格）
        row = []
        for c in cells:
            txt = ''.join(md_inline(x) for x in c.children).strip()
            # Markdown 表格单元格内换行用 <br>
            txt = re.sub(r'\n+', '<br>', txt).replace('|', '\\|')
            row.append(txt)
        if not row:
            continue
        if tr.find('th'):
            headers = row
        else:
            rows.append(row)
    if not headers and rows:
        headers = rows[0]; rows = rows[1:]
    if not headers:
        return ''
    lines = ['| ' + ' | '.join(headers) + ' |',
             '| ' + ' | '.join('---' for _ in headers) + ' |']
    for r in rows:
        # 补齐列数
        while len(r) < len(headers):
            r.append('')
        lines.append('| ' + ' | '.join(r[:len(headers)]) + ' |')
    return '\n'.join(lines)

def md_list(ul_or_ol, depth=0):
    """嵌套列表转 Markdown"""
    is_ord = ul_or_ol.name == 'ol'
    lines = []
    for i, li in enumerate(ul_or_ol.find_all('li', recursive=False), 1):
        prefix = '  ' * depth + (f'{i}. ' if is_ord else '- ')
        # 取 li 直接子节点（不含嵌套 ul/ol 的内容）
        inline_parts = []
        nested = []
        for c in li.children:
            if isinstance(c, Tag) and c.name in ('ul', 'ol'):
                nested.append(c)
            else:
                inline_parts.append(md_inline(c))
        text = ''.join(inline_parts).strip()
        # 单行化
        text = re.sub(r'\s*\n\s*', ' ', text).strip()
        lines.append(prefix + text)
        for n in nested:
            lines.append(md_list(n, depth + 1))
    return '\n'.join(lines)

def md_block(el):
    """处理 body 下的块级元素"""
    if not isinstance(el, Tag):
        s = str(el).strip()
        return s if s else ''

    # 原型图占位
    if is_prototype_div(el):
        idx = proto_divs.index(el) + 1
        # 提取图说明（最后一个 div with text-align:center 或最后的 div）
        caption_el = el.select_one('div[style*="text-align:center"]') or el.find_all('div')[-1] if el.find_all('div') else None
        caption = caption_el.get_text(' ', strip=True) if caption_el else ''
        cap_md = f'\n_{caption}_\n' if caption.startswith('图：') else ''
        return f'\n![原型图{idx}](placeholder-{idx})\n{cap_md}'

    # 架构图 (mindmap)：取所有 li 文本，转嵌套列表
    if is_mindmap_div(el):
        roots = el.find_all('ul', recursive=False)
        return '\n'.join(md_list(r) for r in roots)

    tag = el.name
    if tag in ('h1',):
        # 跳过 H1：飞书文档标题由用户在飞书里设置的节点名决定，
        # HTML 的 H1 不应该重复作为 heading1 块出现在正文里
        return ''
    if tag == 'h2':
        return f'## {el.get_text(strip=True)}\n'
    if tag == 'h3':
        return f'### {el.get_text(strip=True)}\n'
    if tag == 'h4':
        return f'#### {el.get_text(strip=True)}\n'
    if tag == 'h5':
        return f'##### {el.get_text(strip=True)}\n'
    if tag == 'p':
        text = ''.join(md_inline(c) for c in el.children).strip()
        return f'{text}\n' if text else ''
    if tag == 'blockquote':
        text = ''.join(md_inline(c) for c in el.children).strip()
        # blockquote 内可能有 <br>，把单独的几行各自加 >
        lines = [f'> {ln}' for ln in re.sub(r'<br\s*/?>', '\n', text).split('\n') if ln.strip()]
        return '\n'.join(lines) + '\n'
    if tag == 'table':
        return md_table(el) + '\n'
    if tag in ('ul', 'ol'):
        return md_list(el) + '\n'
    if tag == 'hr':
        return '---\n'
    if tag == 'div':
        # 普通 div：递归处理子元素
        return '\n'.join(filter(None, (md_block(c) for c in el.children)))
    return ''

md_parts = []
for child in body.children:
    out = md_block(child)
    if out and out.strip():
        md_parts.append(out)

MARKDOWN = '\n\n'.join(md_parts)
# 清理多余空行
MARKDOWN = re.sub(r'\n{3,}', '\n\n', MARKDOWN)
md_path = WORK / 'final.md'
md_path.write_text(MARKDOWN, encoding='utf-8')
print(f'Markdown 已生成: {md_path} ({len(MARKDOWN)} 字符)')

# ---------------- 3. 把每个原型图 div 包装为独立 HTML，渲染 PNG ----------------
print(f'\n开始渲染 {len(proto_divs)} 张原型图...')

# 模板（与 PRD 共享样式）
HTML_WRAPPER = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; padding: 20px; background: #fff; color: #333; }}
  * {{ box-sizing: border-box; }}
</style>
</head><body>
{content}
</body></html>"""

png_paths = []
for i, div in enumerate(proto_divs, 1):
    html_file = WORK / f'proto-{i}.html'
    png_file = WORK / f'proto-{i}.png'
    html_file.write_text(HTML_WRAPPER.format(content=str(div)), encoding='utf-8')
    # 渲染
    cmd = [
        CHROME, '--headless', '--disable-gpu', '--no-sandbox',
        '--hide-scrollbars',
        '--window-size=940,3000',  # 高度给足，渲染后裁剪
        '--default-background-color=ffffffff',
        f'--screenshot={png_file}',
        f'file://{html_file}'
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if not png_file.exists():
        print(f'  [{i}] 渲染失败: {res.stderr[:200]}')
        continue
    # 自动裁剪底部白边
    try:
        from PIL import Image, ImageChops
        img = Image.open(png_file).convert('RGB')
        bg = Image.new('RGB', img.size, (255, 255, 255))
        diff = ImageChops.difference(img, bg)
        bbox = diff.getbbox()
        if bbox:
            l, t, rt, bt = bbox
            bt = min(img.size[1], bt + 20)
            img.crop((0, 0, img.size[0], bt)).save(png_file)
    except ImportError:
        # 兜底：用 sips 裁剪到尺寸（无法自动算白边，跳过）
        pass
    sz = subprocess.run(['sips', '-g', 'pixelWidth', '-g', 'pixelHeight', str(png_file)], capture_output=True, text=True).stdout
    w = int(re.search(r'pixelWidth:\s*(\d+)', sz).group(1))
    h = int(re.search(r'pixelHeight:\s*(\d+)', sz).group(1))
    print(f'  [{i}] OK  {png_file.name}  {w}x{h}px')
    png_paths.append(png_file)

print(f'渲染完成: {len(png_paths)}/{len(proto_divs)}')

# ---------------- 4. 飞书 API：换 token ----------------
print('\n[飞书] 换取 tenant_access_token ...')
r = requests.post(f'{BASE}/auth/v3/tenant_access_token/internal',
                  json={'app_id': APP_ID, 'app_secret': APP_SECRET})
tok_resp = r.json()
assert tok_resp.get('code') == 0, f'token 失败: {tok_resp}'
TOKEN = tok_resp['tenant_access_token']
HEAD = {'Authorization': f'Bearer {TOKEN}'}
print(f'  ✓ token: {TOKEN[:12]}...')

# ---------------- 5. 解析目标文档 URL，拿真实 doc_id ----------------
print('\n[飞书] 解析目标文档 URL ...')
m = re.search(r'/(docx|wiki)/([A-Za-z0-9]+)', TARGET_URL)
if not m:
    print(f'  ✗ 无法从 URL 解析 token: {TARGET_URL}'); sys.exit(1)
url_type, url_token = m.group(1), m.group(2)
print(f'  类型={url_type}  token={url_token}')

if url_type == 'wiki':
    # 把 wiki token 转成实际 docx doc_id
    r = requests.get(f'{BASE}/wiki/v2/spaces/get_node',
                     headers=HEAD, params={'token': url_token})
    resp = r.json()
    if resp.get('code') != 0:
        print(f'  ✗ wiki get_node 失败: {resp}'); sys.exit(1)
    node = resp['data']['node']
    if node.get('obj_type') != 'docx':
        print(f'  ✗ 节点不是 docx 类型: obj_type={node.get("obj_type")}'); sys.exit(1)
    DOC_ID = node['obj_token']
    print(f'  ✓ wiki → docx: {DOC_ID}')
else:
    DOC_ID = url_token
DOC_URL = TARGET_URL

# ---------------- 5b. 清空文档现有 blocks ----------------
print('\n[飞书] 清空目标文档现有 blocks ...')
r = requests.get(f'{BASE}/docx/v1/documents/{DOC_ID}/blocks',
                 headers=HEAD, params={'page_size': 500})
resp = r.json()
if resp.get('code') != 0:
    print(f'  ✗ 列 blocks 失败: {resp}'); sys.exit(1)
existing = resp['data']['items']
# 根块（page block，block_type=1）保留；删除根块下所有 children
root_block = next((b for b in existing if b['block_type'] == 1), None)
if root_block is None:
    print('  ✗ 找不到根块'); sys.exit(1)
children_count = sum(1 for b in existing if b.get('parent_id') == root_block['block_id'])
print(f'  根块 {root_block["block_id"][:14]}... 有 {children_count} 个直接 children')
if children_count > 0:
    r = requests.delete(f'{BASE}/docx/v1/documents/{DOC_ID}/blocks/{DOC_ID}/children/batch_delete',
                        headers={**HEAD, 'Content-Type': 'application/json'},
                        json={'start_index': 0, 'end_index': children_count})
    resp = r.json()
    if resp.get('code') != 0:
        print(f'  ✗ 清空失败: {resp}'); sys.exit(1)
    print(f'  ✓ 已清空 {children_count} 个 children')
else:
    print('  - 已经是空文档，无需清空')

# ---------------- 6. Markdown 转 blocks ----------------
print('\n[飞书] Markdown 转 blocks ...')
r = requests.post(f'{BASE}/docx/v1/documents/blocks/convert',
                  headers={**HEAD, 'Content-Type': 'application/json'},
                  json={'content_type': 'markdown', 'content': MARKDOWN})
resp = r.json()
assert resp.get('code') == 0, f'转换失败: {resp}'
data = resp['data']
blocks = data['blocks']
first_level = data['first_level_block_ids']
img_url_map = data.get('block_id_to_image_urls', {})
print(f'  ✓ blocks={len(blocks)}, 顶层={len(first_level)}, image_blocks={len(img_url_map)}')

# ---------------- 8. 清理 blocks ----------------
# Table block (31) 去除 merge_info；记录图片块 ID（按 placeholder 序号排序）
TABLE_TYPE = 31
for b in blocks:
    if b.get('block_type') == TABLE_TYPE:
        prop = b.get('table', {}).get('property', {})
        if 'merge_info' in prop:
            del prop['merge_info']

# 按 blocks 数组顺序提取 image block_id（block_type=27 = Image）
# convert API 把 Markdown 里的 ![](placeholder-N) 按出现顺序转成 image block，
# 顺序与我们生成 PNG 的顺序一致
IMG_TYPE = 27
image_block_ids = [b['block_id'] for b in blocks if b.get('block_type') == IMG_TYPE]
print(f'  ✓ image block ids: {[b[:8]+"..." for b in image_block_ids]}')

# ---------------- 9. 用 descendant 接口插入嵌套块 ----------------
print('\n[飞书] 插入嵌套块（descendant 接口）...')
r = requests.post(f'{BASE}/docx/v1/documents/{DOC_ID}/blocks/{DOC_ID}/descendant',
                  headers={**HEAD, 'Content-Type': 'application/json'},
                  json={
                      'children_id': first_level,
                      'descendants': blocks,
                      'index': 0,
                  })
resp = r.json()
if resp.get('code') != 0:
    print(f'  ✗ 插入失败: {resp}')
    sys.exit(1)
print(f'  ✓ 已插入 {len(blocks)} 块到文档')
# descendant API 返回的实际 block 列表（含真实 block_id）
inserted_descendants = resp['data'].get('descendants', []) or resp['data'].get('children', [])
real_image_block_ids = [b['block_id'] for b in inserted_descendants if b.get('block_type') == IMG_TYPE]
print(f'  ✓ 真实 image block ids: {[b[:10]+"..." for b in real_image_block_ids]}')
if real_image_block_ids:
    image_block_ids = real_image_block_ids
time.sleep(0.5)

# ---------------- 10. 上传图片素材（parent_node=ImageBlockID）+ 绑定 ----------------
print(f'\n[飞书] 按图片块上传 + 绑定 ({len(image_block_ids)} 个) ...')
assert len(image_block_ids) == len(png_paths), f'图片块数 ({len(image_block_ids)}) 与 PNG 数 ({len(png_paths)}) 不匹配'

ok = 0
for i, (bid, p) in enumerate(zip(image_block_ids, png_paths), 1):
    # 上传图片素材：parent_node 用图片块 ID
    size = p.stat().st_size
    with open(p, 'rb') as f:
        files = {
            'file_name': (None, p.name),
            'parent_type': (None, 'docx_image'),
            'parent_node': (None, bid),
            'size': (None, str(size)),
            'file': (p.name, f, 'image/png'),
        }
        r = requests.post(f'{BASE}/drive/v1/medias/upload_all', headers=HEAD, files=files)
    up = r.json()
    if up.get('code') != 0:
        print(f'  [{i}] ✗ 上传失败: {up}')
        continue
    ft = up['data']['file_token']
    # 绑定 replace_image
    r = requests.patch(f'{BASE}/docx/v1/documents/{DOC_ID}/blocks/{bid}',
                       headers={**HEAD, 'Content-Type': 'application/json'},
                       json={'replace_image': {'token': ft}})
    resp = r.json()
    if resp.get('code') == 0:
        ok += 1
        print(f'  [{i}] ✓ block {bid[:10]}... ← {ft[:14]}...')
    else:
        print(f'  [{i}] ✗ replace_image: {resp}')
    time.sleep(0.35)

print(f'\n图片绑定完成: {ok}/{len(image_block_ids)}')

# ---------------- 11. 向上回链：父节点 + 祖父节点 ----------------
import urllib.parse as _up

def _wiki_get_node(t):
    r = requests.get(f'{BASE}/wiki/v2/spaces/get_node', headers=HEAD, params={'token': t})
    d = r.json()
    if d.get('code') != 0:
        return None
    return d['data']['node']

def _list_root_children(doc_id):
    r = requests.get(f'{BASE}/docx/v1/documents/{doc_id}/blocks',
                     headers=HEAD, params={'page_size': 500})
    items = r.json()['data']['items']
    root = next((b for b in items if b['block_type'] == 1), None)
    children = [b for b in items if b.get('parent_id') == (root['block_id'] if root else None)]
    return root, children

def _bullet_link_url(bullet_block):
    """提取一个 bullet block 的第一个 text_run 的 link.url（已解码）"""
    if bullet_block.get('block_type') != 12:
        return None
    for e in bullet_block.get('bullet', {}).get('elements', []):
        link = e.get('text_run', {}).get('text_element_style', {}).get('link', {}).get('url', '')
        if link:
            return _up.unquote(link)
    return None

def link_back_one(parent_doc_id, item_url, item_title, brief_text=None, update_existing=True, label=''):
    """在 parent_doc_id 的根块下追加/更新指向 item_url 的 bullet"""
    root, children = _list_root_children(parent_doc_id)
    if root is None:
        print(f'  [{label}] ✗ 父节点找不到根块')
        return 'error'

    existing_bid = None
    for b in children:
        url = _bullet_link_url(b)
        if url and url == item_url:
            existing_bid = b['block_id']
            break

    md_line = f'- [{item_title}]({item_url})'
    if brief_text:
        md_line += f' — {brief_text}'

    if existing_bid:
        if not update_existing:
            print(f'  [{label}] - 跳过（已存在指向 {item_url[-20:]}）')
            return 'skipped'
        # 构造新 elements，PATCH 替换
        url_enc = _up.quote(item_url, safe='')
        elements = [
            {'text_run': {'content': item_title,
                          'text_element_style': {'link': {'url': url_enc}}}}
        ]
        if brief_text:
            elements.append({'text_run': {'content': f' — {brief_text}'}})
        r = requests.patch(f'{BASE}/docx/v1/documents/{parent_doc_id}/blocks/{existing_bid}',
                           headers={**HEAD, 'Content-Type': 'application/json'},
                           json={'update_text_elements': {'elements': elements}})
        d = r.json()
        if d.get('code') == 0:
            print(f'  [{label}] ✓ 更新已存在的 bullet ({existing_bid[:10]}...)')
            return 'updated'
        print(f'  [{label}] ✗ PATCH 失败: {d}')
        return 'error'

    # 不存在：convert + descendant append
    r = requests.post(f'{BASE}/docx/v1/documents/blocks/convert',
                      headers={**HEAD, 'Content-Type': 'application/json'},
                      json={'content_type': 'markdown', 'content': md_line})
    cv = r.json()['data']
    r = requests.post(f'{BASE}/docx/v1/documents/{parent_doc_id}/blocks/{parent_doc_id}/descendant',
                      headers={**HEAD, 'Content-Type': 'application/json'},
                      json={'children_id': cv['first_level_block_ids'],
                            'descendants': cv['blocks'],
                            'index': len(children)})
    d = r.json()
    if d.get('code') == 0:
        print(f'  [{label}] ✓ 追加新 bullet')
        return 'appended'
    print(f'  [{label}] ✗ descendant 失败: {d}')
    return 'error'

print('\n[飞书] 向上回链：父节点 + 祖父节点 ...')

# 解析当前 PRD 节点（用之前从 URL 提取的 token / wiki 类型）
current_node = None
if url_type == 'wiki':
    current_node = _wiki_get_node(url_token)
else:
    # docx 类型暂不支持回链（没法知道在 wiki 树里的位置）
    print('  跳过：当前文档不是 wiki 节点，无法定位父级')

parent_node = _wiki_get_node(current_node['parent_node_token']) if current_node and current_node.get('parent_node_token') else None
gp_node = _wiki_get_node(parent_node['parent_node_token']) if parent_node and parent_node.get('parent_node_token') else None

# 从 TARGET_URL 提取 host，用于构造其他节点的 wiki URL
import urllib.parse as _up2
_host = _up2.urlparse(TARGET_URL).netloc

if parent_node:
    print(f'  父节点：{parent_node["title"]!r}')
    # 写入：当前 PRD 链接 + 需求目标摘要
    link_back_one(
        parent_doc_id=parent_node['obj_token'],
        item_url=TARGET_URL,
        item_title=current_node['title'],
        brief_text=BRIEF or None,
        update_existing=True,
        label='父级',
    )
else:
    print('  跳过：当前 PRD 没有父节点')
    parent_node = None

if gp_node and parent_node:
    print(f'  祖父节点：{gp_node["title"]!r}')
    parent_wiki_url = f'https://{_host}/wiki/{parent_node["node_token"]}'
    # 写入：父节点链接（不带 brief，存在则跳过）
    link_back_one(
        parent_doc_id=gp_node['obj_token'],
        item_url=parent_wiki_url,
        item_title=parent_node['title'],
        brief_text=None,
        update_existing=False,
        label='祖父级',
    )
elif parent_node:
    print('  跳过：父节点没有再上一级，无祖父节点')

# ---------------- 12. 自动同步到云效需求描述 ----------------
print('\n[云效] 同步飞书 URL 到对应需求描述 ...')

def _find_aliyuncs_cfg(start_paths):
    """从一组起点向上查找最近的 .aliyuncs.json"""
    for start in start_paths:
        if not start:
            continue
        p = Path(start).resolve()
        if p.is_file():
            p = p.parent
        while True:
            c = p / '.aliyuncs.json'
            if c.exists():
                return c
            if p == p.parent:
                break
            p = p.parent
    return None

# 找配置文件：先 HTML 所在路径向上，再 cwd 向上（HTML 可能在 /tmp，aliyuncs 在项目目录）
_acfg_path = _find_aliyuncs_cfg([HTML_PATH, Path.cwd()])
if not _acfg_path:
    print('  跳过：未找到 .aliyuncs.json（HTML 路径附近向上无云效配置）')
else:
    _acfg = json.load(open(_acfg_path))
    _reqs = _acfg.get('requirements', [])
    # 按 feishu_url 精确匹配
    _matched = next((r for r in _reqs if r.get('feishu_url') == TARGET_URL), None)
    if not _matched:
        print(f'  跳过：.aliyuncs.json 里没有 feishu_url == {TARGET_URL[-30:]} 的需求')
        print(f'         （如果是新工作流，aliyuncs:create-requirement 时应已写入 feishu_url）')
    else:
        _rid = _matched['identifier']
        try:
            from alibabacloud_devops20210625.client import Client as _AyClient
            from alibabacloud_tea_openapi.models import Config as _AyConfig
            from alibabacloud_devops20210625.models import UpdateWorkItemRequest as _UpdateReq
        except ImportError:
            print('  跳过：缺少 alibabacloud_devops20210625 SDK，运行 `pip3 install alibabacloud-devops20210625` 后重试')
        else:
            _aycfg = _AyConfig(
                access_key_id=_acfg['accessKeyId'],
                access_key_secret=_acfg['accessKeySecret'],
                endpoint='devops.cn-hangzhou.aliyuncs.com',
            )
            _ayclient = _AyClient(_aycfg)
            try:
                _info = _ayclient.get_work_item_info(_acfg['organizationId'], _rid)
                _original = _info.body.workitem.document or ''
            except Exception as _e:
                print(f'  ✗ 读云效需求失败: {_e}')
                _original = None

            if _original is not None:
                _link_line = f'📄 [PRD 文档]({TARGET_URL})'
                # 查重：如果第一行已有指向同 URL 的 PRD 链接，替换；否则顶部插入
                _lines = _original.split('\n', 1)
                _first = _lines[0] if _lines else ''
                if TARGET_URL in _first and 'PRD' in _first:
                    _rest = _lines[1] if len(_lines) > 1 else ''
                    _new_doc = f'{_link_line}\n{_rest}'
                    _action = '替换顶部 PRD 链接'
                else:
                    _new_doc = f'{_link_line}\n\n{_original}' if _original.strip() else _link_line
                    _action = '在顶部插入 PRD 链接'

                if _new_doc != _original:
                    try:
                        _ayclient.update_work_item(_acfg['organizationId'], _UpdateReq(
                            identifier=_rid,
                            field_type='description',
                            property_key='description',
                            property_value=_new_doc,
                        ))
                        print(f'  ✓ 云效需求 {_rid[:10]}... 已{_action}')
                    except Exception as _e:
                        print(f'  ✗ 更新云效需求失败: {_e}')
                else:
                    print(f'  - 云效需求 {_rid[:10]}... 顶部 PRD 链接已是最新，无需修改')

# ---------------- 完成 ----------------
print('\n=' * 30)
print(f'✓ 飞书 PRD 已发布')
print(f'  标题: {PRD_TITLE}')
print(f'  链接: {DOC_URL}')
print(f'  原型图: {ok}/{len(png_paths)} 张')
print(f'  Block: {len(blocks)} 个')
print('=' * 30)
