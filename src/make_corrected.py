"""由 transcript.json 生成 AI 修正版字幕对照稿 transcript.corrected.txt。

原则（用户约定）：逐段保留讲师原始字词与顺序，不合并、不改写为书面语；
仅做两类修改——(1) ASR 错词替换（MAP）；(2) 口癖清理（纯语气词整段删除、
句尾语气词剥离、单字口吃叠词折叠）。MAP 可按视频扩充。

用法: python make_corrected.py <video_id> [<video_id> ...] | --all
可选 --edits <corrections.json>：AI 校订提案作为 MAP 之后的第二遍叠加应用
（逐条校验段号/原文/类别/理由/变更比例，源哈希防错版），并产出审计报告
transcript.corrections.json；不传 --edits 时行为与旧版完全一致。
"""
import argparse
import difflib
import hashlib
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def hhmmss(ts: str) -> str:
    """把 MM:SS 或 HH:MM:SS 统一成 HH:MM:SS，便于人工查看长视频时间戳。"""
    parts = [int(x) for x in str(ts).split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, s = parts[-3:]
    return f"{h + m // 60:02d}:{m % 60:02d}:{s:02d}"


# ASR 错词 -> 正确词（按长度降序应用，避免子串误伤）
MAP = {
    "深圳市软件工程": "生成式软件工程",
    "英拉SEMBLY": "内联汇编",
    "英外SAMBLY": "内联汇编",
    "inline sembly": "内联汇编",
    "英line sembly": "内联汇编",
    "chain of salt": "chain of thought",
    "chal thought": "chain of thought",
    "chef s": "chain of thought",
    "chap out": "chain of thought",
    "chp out": "chain of thought",
    "CHAPSP": "chain of thought",
    "test time skilling": "test-time scaling",
    "试time skilling": "test-time scaling",
    "cloud opo4.5": "Claude Opus 4.5",
    "MANUEL伯纳姆": "Manuel Blum",
    "hugin face": "Hugging Face",
    "open street map": "OpenStreetMap",
    "home brew": "Homebrew",
    "exterminate js": "xterm.js",
    "xterm js": "xterm.js",
    "deep sv4flash": "DeepSeek",
    "deep sick with the flash": "DeepSeek",
    "deep pick": "DeepSeek",
    "deep chick": "DeepSeek",
    "D4C": "DeepSeek",
    "DIVSK": "DeepSeek",
    "KIMIK3": "Kimi K3",
    "GPT5.6": "GPT-5.6",
    "GBT5.6": "GPT-5.6",
    "GPP5.6": "GPT-5.6",
    "GP5.6": "GPT-5.6",
    "GPT56": "GPT-5.6",
    "cheat gp d": "ChatGPT",
    "CHEGBT": "ChatGPT",
    "拆GBT": "ChatGPT",
    "拆GPT": "ChatGPT",
    "拆GPA": "ChatGPT",
    "terry machine": "Turing machine",
    "church tcs": "Church-Turing 论题",
    "habalton pass": "哈密顿路径",
    "ham alton": "哈密顿",
    "three reset": "3-SAT",
    "justin time": "just-in-time",
    "include pass": "include path",
    "yo mode": "YOLO mode",
    "low list": "allowlist",
    "AI slap": "AI slop",
    "passer": "parser",
    "sober": "solver",
    "agents点MD": "agents.md",
    "AGENTS点MD": "agents.md",
    "agent4点MD": "agents.md",
    "agency md": "agents.md",
    "H4点MD": "agents.md",
    "卢卡": "LUCA",
    "杠I": "-I",
    "在ID里": "在 IDE 里",
    "ID里面": "IDE 里面",
    "ID的": "IDE 的",
    "GBT": "ChatGPT",
    "威尔法尔": "verifier",
    "威尔法": "verifier",
    "VERIFILE": "verifier",
    "VERIFI": "verifier",
    "WIFI": "verifier",
    "linux": "Linux",
    # ── BV1kybV6DE47 软件仓库管理（本地 large-v3 ASR 稿）──
    "GP16": "GPT-6",
    "GP6": "GPT-6",
    "GP5.6": "GPT-5.6",
    "GP5": "GPT-5",
    "义父楼": "逸夫楼",
    "光山玩具": "光栅玩具",
    "光山尺": "光栅尺",
    "巨深赛道": "具身赛道",
    "操系统": "操作系统",
    "外部": "外包",
    "webcoding": "vibe coding",
    "web coding": "vibe coding",
    "webcode": "vibe code",
    "Vichy Studio": "Visual Studio",
    "hello.ce": "hello.c",
    "hello.ca": "hello.c",
    "git积交": "git 提交",
    "Basic Practice": "best practice",
    "confessional commits": "Conventional Commits",
    "chat gpg": "ChatGPT",
    "fixed井三": "fixes #3",
    "井三": "#3",
    ".ds-store": ".DS_Store",
    ".dstor": ".DS_Store",
    "DS Store": ".DS_Store",
    "command and fund": "command not found",
    "GH或者GLab": "gh 或者 glab",
    "GLab": "glab",
    "一个go说": "一个 goal 说",
    "汉诺坦": "汉诺塔",
    "双机": "双击",
    "灵光一线": "灵光一现",
    "巨声无比": "巨大无比",
    "bysect": "bisect",
    "by set": "bisect",
    "Community History": "commit history",
    "computer object": "commit object",
    "committed object": "commit object",
    "committed message": "commit message",
    "CommitMessage": "commit message",
    "hide是指向": "HEAD 是指向",
    "ZXY的循环": "X、Y、Z 的循环",
    "就可以出科技": "就可以出效果",
    "都是AIS了": "都是 AI slop 了",
    "一个ATI": "一个 API",
    "cs6ea": "cs61a",
    "learn git branching.js.org": "learngitbranching.js.org",
    "Bitkeeper": "BitKeeper",
    "ProGit": "Pro Git",
    "Git Unity": "git init",
    "git unity": "git init",
    "off by onein strlencheck": "off-by-one in strlen check",
    "state of art": "state of the art",
    "Virtual Implement就": "Virtual Implementation 就",
    "NEO VM": "Neovim",
    "MPM": "npm",
    "cherrypick": "cherry-pick",
    "Implantation": "Implementation",
    "Intent and Spat": "Intent 和 Spec、",
    "Information的空间": "Implementation 的空间",
    "Redmi": "README",
    "Readme": "README",
    "AI Stop": "AI Slop",
    "deep-seek": "DeepSeek",
    "全大学会": "全大写会",
    "前移默化": "潜移默化",
    "不定的变好": "不停地变好",
    "省上要的": "省 token 的",
    "快招": "快照",
    "测试用力": "测试用例",
    "报打好": "包打好",
    "或者流打": "或者流水线",
    "CICD": "CI/CD",
    "precommitted hook": "pre-commit hook",
    "interment": "int main(void)",
    "intimate void": "int main(void)",
    "监控号": "尖括号",
    "叫hours": "叫 ours",
    "可以reveal": "可以 revert",
    "agency.md": "AGENTS.md",
    "agent.cmd": "AGENTS.md",
    "考案神": "convention",
    "超系统课": "计算机系统课",
    # ── BV1Q6en6NEUo 软件仓库管理(2)（B 站 ai-zh 字幕）──
    "web code": "vibe code",
    "A证": "agent", "A政": "agent", "A震": "agent",
    "交流坑": "焦油坑",
    "AI is lap": "AI slop", "a s lap": "AI slop", "AISLOFT": "AI slop",
    "slot out": "slop", "生成SP2": "生成 slop",
    "get it work tree": "git worktree",
    "get it by sec": "git bisect", "get it blame": "git blame",
    "get it report": "git repo", "get it ripple": "git repo",
    "Get it": "git", "get it": "git", "gate": "git",
    "点get": ".git", "ripple": "repo",
    "rapport点BB": "repo.db", "report点dB": "repo.db",
    "GGT": "jj", "GG词": "jj", "GG子": "jj", "JUJS": "jj", "JUSS": "jj",
    "句句词": "Jujutsu", "JJS": "jj",
    "瑞贝斯": "rebase",
    "REBASESTHSTH": "rebase stash",
    "get sth": "git stash", "STH": "stash", "statch": "stash", "STATCH": "stash", "SSTACK": "stash stack",
    "t max": "tmux", "tm session": "tmux session", "体Mark": "tmux",
    "work tree": "worktree", "WALKTHROUGH": "worktree", "WORKTI": "worktree",
    "WORKT吗": "worktree 上吗", "walk around": "workaround",
    "deep pick": "DeepSeek", "DPCV4flash": "DeepSeek V4 Flash", "desk v4": "DeepSeek V4",
    "cloud code": "Claude Code", "Cloud code": "Claude Code",
    "oor leaf": "Overleaf",
    "subversion": "subagent",
    "哈洛塔": "汉诺塔",
    "variable product": "viable product", "PARAA": "paradigm",
    "S mail": "email", "SMAIL": "email",
    "L1号": "一卡通", "一号": "一卡通",
    "skin log": "scaling law",
    "播骷髅": "workflow",
    "adversary lock": "advisory lock",
    "C口查询": "SQL 查询",
    "主威镇": "主 agent", "主位制": "主座位",
    "traction的": "transaction 的", "traction sq说": "transaction 说",
    "BT": "abort", "OLBOT": "abort",
    "singles ready": "single-threaded", "single studi": "single-threaded", "single spread": "single-threaded",
    "a j mod": "agent mode",
    "spring shots": "screenshots",
    "SPICATION": "specification",
    "COMMERCISCIENCE": "computer science", "converter science": "computer science",
    "TRACABILITY": "traceability", "suffer trace ability": "software traceability",
    "seating error": "staging area",
    "persistent data加structure": "persistent data structure",
    "SPN": "SVN",
    "PARADIM": "paradigm",
    "git点NHU点E点点CN": "git.nju.edu.cn",
    "three bet": "rebase",
    "computing m": "contributing.md", "contributing点MD": "contributing.md",
    "现行历史": "线性历史",
    "read me点MD": "README.md", "read me": "README",
    "C加加": "C++",
    "点text文件": ".tex 文件",
    "pickle playground": "playground",
    "idol了": "edit 了",
    "GTT起": "GPT 也", "原原话": "原话",
    "SISTANT点dB": "assistant.db",
    "da base": "database",
    "VTREE": "worktrees", "GDIR": "gitdir:",
    # ── BV1Nyeq6qEt8 软件工程的来龙去脉（B 站 ai-zh 字幕）──
    "type c AI": "TypeSafe AI",
    "system one": "System One",
    "prefer only": "prefill-only",
    "JEFF": "Jev", "JB这样的模型": "Jev 这样的模型",
    "CHAMPSHO": "chain of thought", "CHAS是": "chain of thought 是",
    "GPUSA": "GPT-6 + Sora", "GP6s pro": "GPT-6s pro",
    "GPT6": "GPT-6", "GPU的token真的非常省": "GPT-6 的 token 真的非常省",
    "gt3": "GPT-3", "GP4O": "GPT-4o", "alex net": "AlexNet", "磁向量": "词向量",
    "BT啊": "BERT 啊",
    "NO brown": "Noam Brown", "all in i r ISI": "all in on RSI",
    "rise recursive improvement": "RSI（recursive self-improvement）",
    "skin law": "scaling law", "skin lo": "scaling law", "skin老师": "scaling law 是说",
    "ENTROPIC": "Anthropic", "ANTHROPY": "Anthropic",
    "基摩场": "基模厂", "机膜厂": "基模厂", "禁摩场": "基模厂", "筋膜训练": "基模训练",
    "机动模型": "基座模型", "反华的效果": "泛化的效果", "road hack": "reward hack",
    "讯推": "训推", "家境这个数据": "加进这个数据", "a e care": "AI 顶会",
    "AI s lop": "AI slop", "swap code": "slop code",
    "豆宝手机": "豆包手机", "德宝手机": "豆包手机", "德报手机": "豆包手机",
    "level print": "label print", "电子墨水瓶": "电子墨水屏",
    "cloud open4.6": "Claude Opus 4.6",
    "196年": "1960 年", "IPHONE18pro": "iPhone 18 Pro", "ICLOUD": "iCloud",
    "达舍尔": "Dijkstra", "DEXTRA": "Dijkstra",
    "camera scientist": "computer scientist", "caputer science": "computer science",
    "puter science": "computer science",
    "HARO": "harmful", "不含破": "不 harmful", "构图": "goto",
    "train lecture": "Turing Lecture", "humhumble": "humble",
    "Nicely factor solutions": "nicely factored solutions",
    "NATTO": "NATO", "HAMILTON": "Hamilton", "哈密尔顿": "Hamilton",
    "SERGEONS": "assertions", "I trio e": "IEEE", "PRIERM": "pre-AI",
    "大于原模型": "大语言模型", "大圆模型": "大语言模型",
    "WINSTONROYCE": "Winston Royce", "imagine the development": "Managing the development",
    "跟rose": "跟 Royce", "rose的": "Royce 的", "rose他": "Royce 他", "rise的": "Royce 的",
    "ROIS的模型": "Royce 的模型", "pom模型": "Royce 模型",
    "breakfast search": "BFS", "breakfast": "BFS", "def search": "DFS",
    "DEFEN性": "dependency", "cos的很高": "cost 很高", "一烫头下来": "一头扎下来",
    "杠dogs": "/docs", "source下": "src 下", "pick check": "QuickCheck",
    "秦刷化": "形式化", "now pointer": "null pointer", "IFL": "Eiffel",
    "霍尔三人组": "Hoare 三元组", "dafany virus": "Dafny、Verus", "恋爱来了": "LLM 来了",
    "SERT": "assert", "ENGLIST": "linked list", "羽翼的对齐": "语义的对齐",
    "latin space": "latent space", "IPU": "UML", "UML9": "UML 就",
    "button map": "bottom-up", "bad smile": "bad smell", "CHEACTI": "checklist",
    "NSIZE赋予了": "nonsense 赋予了", "干水教材": "灌水教材", "财政能力": "才智",
    "反攻代价": "返工代价", "反攻的概率": "返工的概率", "700币": "7B", "VIVO50": "50 美元",
    "DPA的": "DARPA 的", "SPECIICATION": "specification", "INTET": "intent",
    "空的rap": "空的 repo", "suffer development model": "software development model",
    "KIMI": "Kimi", "CIVISION": "division", "UMR": "UML",
    "u m l spec": "UML spec", "u m spec": "UML spec", "流感": "留白",
    "AICPLOT": "AI PPT", "make size的skill": "make slides 的 skill",
    "boys life9月号": "Boys' Life 9 月号", "boys life": "Boys' Life",
    "DPPK": "DeepSeek", "blender": "Blender", "doc x": "docx",
    "online价值": "online judge", "用这个LP": "用这个 LPD",
    "2500并发的底薪": "2500 并发的低薪码农", "trace ability": "traceability",
    "data defencies": "data dependency", "android": "Android",
    # ── BV1Rch76WEfQ 需求和架构 (1)（B 站 ai-zh 字幕稿）──
    "ris is批判": "Royce 批判", "ROYCE": "Royce",
    "cs making": "CSRankings", "ECISE": "ICSE",
    "APRAI": "pre-AI", "U m l": "UML",
    "TRACABILITY": "traceability", "TRABILITY": "traceability",
    "SDE": "stdin", "silence erro": "silent error",
    "minimal marvel product": "minimum viable product",
    "swap铺开": "slop 铺开", "slap污染": "slop 污染",
    "GB6": "GPT-6", "gt6": "GPT-6", "GT6": "GPT-6",
    "deep sk": "DeepSeek", "deep pk": "DeepSeek",
    "live1": "Lab 1", "DEPENDC": "depend", "DEPON": "depend", "DE盘": "depend",
    "CRI的架构": "client-server 的架构", "CIRI": "client-server", "CONSERVER": "client-server",
    "CI点PY": "cli.py", "COCODE": "Claude Code", "dB点ts": "db.ts",
    "JAVASCRIPT": "JavaScript", "PAGENT": "PyAgent",
    "java系统": "教务系统", "交互系统": "教务系统", "撬务系统": "教务系统",
    "仙灵": "仙林", "仙一": "仙林", "木刻": "慕课", "缺克": "缺课",
    "技术站": "技术债", "技术宅": "技术债", "Technical de": "technical debt",
    "史山": "屎山", "石山": "屎山", "使臣": "屎山", "屎缠": "屎山",
    "TDS": "tedious", "job box": "combobox", "jobbox": "combobox",
    "保研机时": "保研机试", "第一次氪": "第一次课", "腾好了": "誊好了", "一把戳": "一把梭",
    "turn complete": "Turing complete", "PYXLC": "py2xl",
    "video cup": "VLOOKUP", "x look up": "XLOOKUP", "extended or卡牌": "extended lookup",
    "LM去编译": "LLM 去编译", "LIM": "LLM",
    "表达式数": "表达式树", "DETERMC": "deterministic", "SIMPLIFICTION": "simplification",
    "infer人": "inference", "MONOLIC": "monolithic", "83KKB": "83KB",
    "item potent": "idempotent", "CLUD": "CRUD",
    "get get it s VN": "git、SVN", "没戏了": "没系了",
    "get opp t": "getopt", "get o b t": "getopt", "get a o p t": "getopt",
    "Painput": "parse input", "passing state": "parsing state", "party state": "parsing state",
    "passing的模式": "parsing 的模式",
    "二个C和阿个V": "argc 和 argv", "阿格V": "argv", "阿哥V": "argv", "二个V": "argv",
    "R个V是二鬼": "argv 和 argc",
    "感兴趣record is": "感兴趣 Redis", "这LS": "Redis",
    "TAO和HANNOWAY": "Tower of Hanoi", "TAOHANNOWAY": "Tower of Hanoi",
    "top hana": "Tower of Hanoi", "ta和HONNI": "Tower of Hanoi",
    "淘宝号": "汉诺塔", "淘宝不跑动": "汉诺塔", "TPHONY": "汉诺塔",
    "tao ho h诺尔": "汉诺塔", "HANOIN减一": "hanoi(n-1)",
    "FADV": "hanoi", "GPU又": "GPT 又", "模拟战": "模拟栈", "NAI在": "AI 在",
    "小部语义": "小步语义", "F调GG调F": "F 调 G、G 调 F", "over kill": "overkill",
    "实行的": "十行的", "一般sourcing": "event sourcing", "一般塑型": "event sourcing",
    "一般缩ING": "event sourcing", "一般索性": "event sourcing",
    "excel": "Excel", "OGACAI": "AI",
    "什么brain": "什么 Brainfuck",
    # ── 需求和架构 (2)（第 07 讲，BV1JGap6LE74）──
    "价格": "架构",
    "DASHA": "Dijkstra",
    "携程": "协程", "县城": "线程",
    "CORRINE": "coroutine", "CORRATING": "coroutine", "corrating": "coroutine",
    "one source": "event sourcing", "一般source": "event sourcing",
    "吹倒夫尼": "trade-off",
    "x dental": "accidental", "C弹头": "accidental", "eessential": "essential",
    "SAAWK": "sed、awk", "quick salt": "qsort",
    "金家兔": "Jinja", "WSA98": "OOPSLA'98", "乌普斯达酒吧": "OOPSLA",
    "EF考": "E. F. Codd", "tony霍尔": "Tony Hoare", "NO point": "null pointer",
    "relation NO database": "relational database", "data gram": "datagram",
    "优侧控制": "拥塞控制", "Cop cop nis": "Kubernetes",
    "IMAX": "Emacs", "WM": "Vim", "不胜战": "互相圣战",
    "cloud": "Claude",
    "STATI": "status", "silently cpt": "silently corrupt",
    "wheel state": "ViewState", "盗墓车": "DOM tree", "盗墓": "DOM", "德奥": "DOM",
    "R f c": "RFC", "RFC191958": "RFC 1958",
    "scheme": "Scheme", "fiber": "Fiber", "react": "React",
    # 介于词/短语层面的同音错词（第二批）
    "problem dwin": "problem domain",
    "minimal variable product": "minimum viable product",
    "right programs will handle tax dreams": "Write programs to handle text streams",
    "go to is harmful": "goto is harmful", "不需要go to": "不需要 goto",
    "abinability": "inability", "amental": "mental",
    "CORROUTINE": "coroutine",
    "DOMDOOMM": "DOM", "DOMM": "DOM", "HML": "HTML",
    "INTETATION": "implementation", "intentATION": "implementation",
    "time space": "intent space", "SHSK": "ICS", "ISS": "ICS", "SSS": "ICS",
    "那个CC": "那个 C", "再XS了": "再 access 了", "DOBE": "Adobe",
    "OJT": "OJ", "MVCMVVM": "MVC / MVVM", "PAYRO": "payroll",
    "PHD": "PhD", "GUE": "GUI", "ULINUX": "Linux", "NEO": "Neovim",
    "tile net": "telnet", "hp上": "HTTP 上", "curing": "curry",
    "SOCING": "sourcing", "souring": "sourcing", "这个ORI的": "这个 override 的",
    "DELBASE": "database", "sickle": "SQL",
    "react scary": "React scheduler", "chi g p t": "ChatGPT",
    "SEO": "SQL", "HTPS": "HTTPS", "java": "Java", "internet": "Internet",
    "unix": "UNIX", "dom tree": "DOM tree", "virtual dom": "virtual DOM",
    "mvc": "MVC", "llm": "LLM", "qr": "QR",
    "DPIJK": "dp[i][j][k]", "AAPI": "API",
    "然后will是一个visual": "然后 View 是一个 visual",
    "所谓的will": "所谓的 View", "will是一个function": "View 是一个 function",
    "然后will就是你看到的那个页面": "然后 View 就是你看到的那个页面",
    "然后这个will": "然后这个 View",
    "是will上面还可以": "是 View，上面还可以",
    "will里当然也可以": "View 里当然也可以",
    "view": "View",
    # 第三批：个别残留错词
    "个DPI": "个 dp[i]", "object oried": "object-oriented",
    "n mem byte": "nmemb", "comcomputer science": "computer science",
    "PHPASP": "PHP / ASP", "被hoover了": "被 hover 了",
    "然后CD里面有一个": "然后里面有一个",
    "杰克就开始说": "我们就开始说",
}
_MAP_ITEMS = sorted(MAP.items(), key=lambda kv: -len(kv[0]))

# 整段即为口癖 -> 删除该段
FILLER_ONLY = {"呃", "嗯", "啊", "哦", "啧", "哎", "哎呀", "哈哈", "哈哈哈", "嘿嘿",
               "对", "对吧", "对啊", "好啊", "好", "好的", "然后", "任何", "额",
               "anyway", "Anyway", "ANYWAY", "呃呃", "嗯嗯", "啊哈", "呜", "喂", "yes", "no"}

# 句尾口癖 -> 剥离
TAIL_FILLER = re.compile(r"(?:对吧|对不对|是吧|是不是|嘛|呀|哦|呃|嗯|哈哈|哈|啊|呢)+$")

# 单字口吃叠词折叠：我我我->我 等
STUTTER = re.compile(r"(我|你|他|它|就|是|有|去|来|啊|呃|嗯|对|但|那|这|也|都|还|又|再|很|太|会|要|想|说|看|做|搞|弄|写|读|问|答|学|教|玩|用|给|把|被|让|使|等)\1+")


def correct(text: str):
    for old, new in _MAP_ITEMS:
        if old in text:
            text = text.replace(old, new)
    text = text.replace("呃", "").replace("嗯", "")
    text = STUTTER.sub(r"\1", text)
    text = TAIL_FILLER.sub("", text).strip()
    return text


# ─────────────────────────────────────────────
# AI 校订提案校验层（叠加在 MAP 之后的第二遍，思想借鉴 PR#1，保持 MAP 与口癖清理不变）
# AI 提交 corrections.json：每条含 segment_index / original / replacement /
# category / reason；脚本校验后应用并产出审计报告 transcript.corrections.json。
# ─────────────────────────────────────────────

CATEGORIES = {"proper_noun", "technical_term", "transcription", "punctuation", "segmentation"}


def source_hash(segments) -> str:
    """transcript.json segments 的指纹，防止校订提案基于错误版本。"""
    canonical = json.dumps(segments, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def apply_ai_edits(segments, baseline: dict, proposal: dict, allow_large: bool = False):
    """把 AI 提案应用到 MAP 之后的基线文本上。baseline: {segment_index: text}。

    校验：源哈希一致、段号合法且不重复、段未被口癖清理删除、original 与基线逐字
   一致、replacement 非空单行、category/reason 必填、大幅修改默认拒绝。
    返回 (applied: {index: new_text}, report: [edit+change_ratio])。"""
    if proposal.get("source_sha256") != source_hash(segments):
        raise ValueError("source_sha256 不匹配：请基于当前 transcript.json 重新生成提案")
    applied, report, seen = {}, [], set()
    for edit in proposal.get("edits", []):
        idx = edit.get("segment_index")
        if type(idx) is not int or not 0 <= idx < len(segments) or idx in seen:
            raise ValueError(f"segment_index 非法或重复: {idx!r}")
        seen.add(idx)
        if idx not in baseline:
            raise ValueError(f"段 {idx} 已被口癖清理删除，不允许校订")
        cur = baseline[idx]
        if edit.get("original") != cur:
            raise ValueError(f"段 {idx} original 与 MAP 后基线文本不一致")
        rep = edit.get("replacement")
        if not isinstance(rep, str) or not rep.strip() or "\n" in rep or "\r" in rep:
            raise ValueError(f"段 {idx}: 禁止删除、空替换或多行替换")
        if edit.get("category") not in CATEGORIES or not str(edit.get("reason", "")).strip():
            raise ValueError(f"段 {idx}: 必须给出合法 category 与非空 reason")
        ratio = 1 - difflib.SequenceMatcher(None, cur, rep).ratio()
        if len(cur) >= 40 and ratio > 0.4 and not allow_large:
            raise ValueError(f"段 {idx}: 大幅修改({ratio:.0%})，人工确认后加 --allow-large-edits")
        applied[idx] = rep
        if rep != cur:
            report.append({**edit, "change_ratio": round(ratio, 4)})
    return applied, report


def main():
    ap = argparse.ArgumentParser(description="生成 AI 修正版字幕对照稿")
    ap.add_argument("video_id", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--edits", metavar="JSON",
                    help="AI 校订提案 corrections.json（叠加在 MAP 之后，仅限单个视频）")
    ap.add_argument("--allow-large-edits", action="store_true",
                    help="允许提案中逐条人工确认过的大幅修改")
    ap.add_argument("--force", action="store_true",
                    help="确认覆盖已存在的 transcript.corrected.txt（其中可能含人工/AI 行级订正）")
    args = ap.parse_args()
    if args.edits and len(args.video_id) != 1:
        ap.error("--edits 仅支持单个 video_id")
    ids = args.video_id or [d for d in sorted(os.listdir(os.path.join(BASE, "output")))
                            if os.path.isfile(os.path.join(BASE, "output", d, "transcript.json"))]
    for vid in ids:
        src = os.path.join(BASE, "output", vid, "transcript.json")
        segs = json.load(open(src, encoding="utf-8"))["segments"]
        entries, dropped, fixed = [], 0, 0
        for i, seg in enumerate(segs):
            raw = seg["text"].strip()
            if raw in FILLER_ONLY:
                dropped += 1
                entries.append((seg, None))
                continue
            txt = correct(raw)
            if txt != raw:
                fixed += 1
            if not txt:
                dropped += 1
                entries.append((seg, None))
                continue
            entries.append((seg, txt))
        baseline = {i: t for i, (seg, t) in enumerate(entries) if t is not None}
        ai_edits = 0
        if args.edits:
            proposal = json.load(open(args.edits, encoding="utf-8"))
            applied, report = apply_ai_edits(segs, baseline, proposal, args.allow_large_edits)
            baseline.update(applied)
            ai_edits = len(report)
            with open(os.path.join(BASE, "output", vid, "transcript.corrections.json"),
                      "w", encoding="utf-8", newline="\n") as f:
                json.dump({"source_sha256": source_hash(segs),
                           "segment_count": len(segs),
                           "status": "applied_ai_edits",
                           "edits": report}, f, ensure_ascii=False, indent=2)
        out_lines = []
        for i, (seg, txt) in enumerate(entries):
            if txt is None:
                continue
            out_lines.append(f"[{hhmmss(seg['start'])}] {baseline[i]}")
        dst = os.path.join(BASE, "output", vid, "transcript.corrected.txt")
        if os.path.exists(dst) and not args.force:
            sys.exit(f"{vid}: transcript.corrected.txt 已存在（可能含人工/AI 行级订正）；"
                     f"确需覆盖请加 --force，或改用 --edits 叠加校订")
        with open(dst, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(out_lines) + "\n")
        print(f"{vid}: {len(segs)} 段 -> {len(out_lines)} 行（MAP 修正 {fixed} 行，"
              f"AI 校订 {ai_edits} 行，删除口癖段 {dropped}）")


if __name__ == "__main__":
    main()
