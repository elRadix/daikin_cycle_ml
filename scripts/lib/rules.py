RULES = {
'R288':'in-code','R298':'in-code','R315':'in-code','R441':'in-code',
'R442':'in-code','R446':'in-code','R447':'in-code','R448':'in-code',
'R449':'in-code','R486':'in-code','R549':'in-code','R555':'in-code',
'R557':'in-code','R580':'in-code','R709':'in-code','R710':'in-code',
'R843':'in-code','R844':'in-code','R845':'in-code','R848':'in-code',
'R798':'git-safe','R819':'git-safe','R825':'git-safe','R833':'git-safe',
'R834':'git-safe','R846':'git-safe','R856':'git-safe','R859':'git-safe',
'R863':'git-safe','R864':'git-safe',
'R791':'pre-release','R795':'pre-release','R797':'pre-release',
'R811':'ci-local','R812':'ci-local','R826':'ci-local','R830':'ci-local',
'R847':'ci-local','R851':'ci-local','R861':'ci-local',
'R857':'pre-commit','R860':'pre-commit',
'R814':'shell-lib','R858':'shell-lib',
'R862':'procedural',
}
def owned_by(o): return sorted(r for r,x in RULES.items() if x==o)
def describe(rid): return f'{rid} [{RULES.get(rid, "unknown")}]'
