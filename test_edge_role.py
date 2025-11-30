# -*- coding: utf-8 -*-
import json
from pathlib import Path

# 直接读取 JSON 文件
voice_file = Path("videotrans/voicejson/edge_tts.json")
with open(voice_file, 'r', encoding='utf-8') as f:
    voice_list = json.load(f)

# 检查 zh 下的所有 key
zh_voices = voice_list.get('zh', {})
print(f"Found {len(zh_voices)} voices in 'zh'")

# 查找包含 "晓晓" 的 key
for key, value in zh_voices.items():
    if '晓晓' in key or 'Xiaoxiao' in key.lower():
        print(f"  Key: {repr(key)} -> {value}")

# 测试精确匹配
test_key = "晓晓(Female/CN)"
result = zh_voices.get(test_key)
print(f"\nExact match for {repr(test_key)}: {result}")

# 写结果到文件
with open("test_edge_result.txt", "w", encoding="utf-8") as f:
    f.write(f"Found {len(zh_voices)} voices in 'zh'\n")
    for key, value in zh_voices.items():
        if '晓晓' in key or 'Xiaoxiao' in key.lower():
            f.write(f"  Key: {repr(key)} -> {value}\n")
    f.write(f"\nExact match for {repr(test_key)}: {result}\n")
