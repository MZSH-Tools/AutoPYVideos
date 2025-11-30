# -*- coding: utf-8 -*-
from videotrans.util import tools
from pathlib import Path

result = tools.get_edge_rolelist('晓晓(Female/CN)', 'zh-cn')
result2 = tools.get_edge_rolelist('晓晓(Female/CN)', 'zh')

# Write to file
Path('test_result.txt').write_text(f"Result zh-cn: {result}\nResult zh: {result2}", encoding='utf-8')
