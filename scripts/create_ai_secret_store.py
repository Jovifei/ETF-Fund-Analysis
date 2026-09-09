"""Create an exclusive private master key; never print secret bytes.
Example: python scripts/create_ai_secret_store.py --path E:\\ETF_Private\\secrets\\ai.key
Existing keys cannot be overwritten. Back up this key separately from the DB.
"""
from pathlib import Path
import argparse
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.workspace.ai_secrets import create_master
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--path',type=Path,required=True);args=parser.parse_args()
    try:create_master(args.path)
    except Exception:
        print('创建失败：文件已存在、路径不受支持或私有目录权限不正确；未覆盖已有密钥。',file=sys.stderr);raise SystemExit(2)
    print('私有主密钥已创建。API 与 worker 必须以同一用户加载 WORKSPACE_AI_KEY_FILE；保留离线备份，不提交 Git。')
