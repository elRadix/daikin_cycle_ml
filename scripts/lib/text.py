import re

_D = re.compile(r'\b(?:het|een|niet|wel|maar|voor|naar|wordt|worden|zijn|heeft|hebben|geen|meer|ook|deze|dat|dit|als|door|over|tussen|tijdens|omdat|onder|boven|nieuw|nieuwe|oude|dezelfde|andere|alle|veel|weinig)\b', re.I)
def has_dutch(t): return bool(_D.search(t))
def line_anchored_replace(c,s,n):
    return re.sub(rf'^## {re.escape(s)}\n.*?(?=^## |\Z)', n, c, flags=re.M|re.S)
