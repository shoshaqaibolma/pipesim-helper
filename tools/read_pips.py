"""Command-line wrapper: print what read_pips finds in a .pips file (read-only, works on a copy).
  "D:\\Program\\Pipesim toolkit\\python.exe" tools\\read_pips.py "C:\\models\\line.pips" [component] [keyword]"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pips_reader

print(json.dumps(pips_reader.read_pips(sys.argv[1], *(sys.argv[2:4])), indent=1, default=str)[:20000])
