#!/usr/bin/env python3
"""
build a tree from a task event DSL
descend tree to build a list of random events

200/10x A=1.5,{B=1.5,0.15*C=1.5,$}<3>,C=1.5;=1.5
  ###/#x   total duraiton/number repeats
  =#.#     duration
  {,}      permutation, tree siblings
  $        catch end
  #.#*     proportion of permutaitons
  <#>      max repeats
  ,        add next in sequence
  ;=#.#    variable iti w/stepsize; end of root node
  
thoughts on duration
  =#.#...#.#  = variable duration
  =#...#(exp) = var exponential

need additional node max/min to when specified for repeats
"""

from parsimonious.grammar import Grammar
from parsimonious.nodes import NodeVisitor
from anytree import Node, RenderTree
task_dsl = Grammar(
    """
    main  = info anyevent+

    info         = total_dur "/" total_trials "x" " "
    total_dur    = float
    total_trials = num

    anyevent    =  ( children / event / catch_end / iti )
    in_children = ( children / event / catch_end / iti )
    children    = "{" in_children+ "}" maxrep? sep?
    catch_end   = "$"
    event       = reps? prop? name dur? maxrep? sep?
    iti = ";" dur?

    name        = ~"[A-Za-z0-9.:_-]+"i
    reps        = num "x"
    prop        = float "*"
    dur         = "=" float dur_range? dur_type?
    dur_range   = "..." float
    dur_type    = "(exp)"
    maxrep      = "<" num ">"
    sep         = ","
    float       = ~"[0-9.]+"
    num         = ~"[0-9]+"
    """
)

class EventMaker(NodeVisitor):
    def visit_main(self, node, children):
        "final collection at 'main' after through all children"
        out = []
        for c in children:
            if not c:
                continue
            if c and type(c) in [list, dict]:
                out.append(c)
        return out

    def visit_info(self, node, children):
        "side effect: update self.total_duraiton and total_trials"
        assert node.expr_name == 'info'
        self.total_duration = children[0]
        self.total_trials = children[2]
        return None

    def visit_event(self, node, children):
        "main node. collects reps? prop? name dur? maxrep? sep?"
        event = {"dur": 1, "descend": True}
        for c in children:
            if not c:
                continue
            elif type(c) == list:
                print(c)
                if c[0] and type(c[0]) == dict:
                    event.update(c[0])
                continue
            elif not c.expr_name:
                continue
            print(c)
            key = c.expr_name
            if key == "name":
                value = c.text
            # these are never hit?
            elif key == "prop":
                value = c.children[0]
            elif key == "dur":
                value = c["dur"]
            elif key == "reps":
                value = c.children[0]
            elif key == "maxrep":
                value = c.children[1]
            else:
                raise Exception(f"unknown event attribute '{key}': '{c}'")
            event[key] = value
        return event
    
    def visit_catch_end(self, node, children):
        "when grammar sees '$', the tree should not be followed down"
        assert not children
        return {'name': "CATCH", "dur": 0, "descend": False}

    def visit_dur(self, node, children):
        # TODO: duration range
        # TODO: duration type
        dur = children[1]
        return {'dur': dur}

    def visit_reps(self, node, children):
        reps = children[1]
        # child[1] is 'x' but now None
        return {'reps': rep}
    def visit_prop(self, node, children):
        # child[1] was '*' but now None
        return {'prop': children[0]}

    def visit_float(self, node, children):
        assert not children
        return float(node.text)

    def visit_num(self, node, children):
        assert not children
        return int(node.text)

    def visit_sep(self, node, children): return None
    def visit_maxsep(self, node, children):
        assert not children
        return int(node.text)
    def generic_visit(self, node, children):
        # remove literals used in grammar
        if node.text in ["{", "}", ">","<", '=', '*']:
            return None
        # remove empty optionals
        if not children and not node.text and not node.expr_name:
            return None
        # things we haven't identified yet (anyevent, in_children)
        return children or node

def shake(l):
    "remove None, empty lists, and raise nested single item lists"
    if type(l) == list:
        l = [shake(x) for x in l if x]
        l = [x for x in l if x]
        if len(l) == 1:
            l = l[0]
    return l

class Event():
    def __init__(self, d:dict):
        self.dur = d.get("dur", 0)
        self.name = d.get("name")
        self.prop = d.get("prop")
        self.descend = d.get("descend", True)
        self.maxrep = d.get("maxrep", -1)

    def __repr__(self):
        disp=f"{self.name}={self.dur}"
        if self.prop:
            disp=f"{self.prop}*{disp}"
        return disp



def build_tree(input_list:list, roots:list=None, append=False):
    """
    progressively add leaves to a tree. returns the final leaf/leaves
    [A,B,C] = A->B->C     (returns [C])
    [A,[B,C],D] = A->B->D
                   ->C->D (returns [D,D])
    """
    if not roots:
        roots = [Node(Event({"name":"root", "prop": 1}))]

    leaves = []
    for n in input_list:
        if type(n) == list:
            print(f"#** {n} is list. recurse")
            roots = build_tree(n, roots, append=True)
        elif append:
            for p in roots:
                if p.name.descend:
                    leaves.append(Node(Event(n), parent=p))
        else:
            roots = [Node(Event(n), parent=p) for p in roots if p.name.descend]
            leaves = roots
        print(f"# leaves: {len(leaves)} @ {n}")
    return leaves

def set_children_proption(node):
    """update node's children 'prop'
    the proportion of trials with this sequence. defaults to symetic"""
    n = len(node.children)
    existing = [x.name.prop for x in node.children if x.name.prop is not None]
    n_remain = n - len(existing)
    if(n_remain<=0):
        return
    start = 1 - sum(existing)
    eq_dist = start / n_remain
    for n in node.children:
        if n.name.prop is None:
            n.name.prop = eq_dist
    # TODO: assert value is close to 1


def clean_tree(node):
    "set proprotions for entire tree"
    set_children_proption(node)
    for n in node.children:
        clean_tree(n)

def find_leaves(node):
    "inefficent. use with shake. find catch leaves"
    if not node.children:
        return node
    return [find_leaves(n) for n in node.children]
            
        

example = task_dsl.parse("100/10x test")
task_dsl.parse("100/10x test=2.5")
task_dsl.parse("100/10x test=2.5<2>")
task_dsl.parse("100/10x .3*test=2.5<2>")
task_dsl.parse("100/10x .3*test=2.5<2>;")
task_dsl.parse("100/10x {one,two}")
task_dsl.parse("100/10x {one,two,{three}}")
task_dsl.parse("100/10x {one,two},three")
task_dsl.parse("100/10x A=1.5,D,{.3*B=.5,C=.3,$},D")

ep = EventMaker()
o = ep.visit(tree)
# ep.total_duration
# ep.total_trials
x = ep.visit(task_dsl.parse("100/10x A=1.5,D,{.15*B=.5,C=.3,$},D"))
print(shake(x))

t = build_tree(shake(x))
root = t[0].root
print(RenderTree(root))

real_leaves = shake(find_leaves(root))
clean_tree(root)
print(RenderTree(root))
print(real_leaves)

def calc_leaf(leaf):
    prop = leaf.name.prop
    dur  = leaf.name.dur
    seq = [leaf.name]
    while leaf.parent:
      n = leaf.parent.name
      prop *= n.prop
      dur  += n.dur
      seq = [n, *seq]
      leaf = leaf.parent
    return {"prop":prop,"dur":dur,"seq":seq}

res = [calc_leaf(l) for l in real_leaves]
print(res)
res = [{**x, "n": int(x['prop']*ep.total_trials)} for x in res]
trials_needed = ep.total_trials - int(sum([x.get("n") for x in res]))
# todo: warning. add to random

# todo. repeat each seq "n" times. intersperce with itis. generate 1d files
