import ast

from pprint import pprint
from time import time_ns
from collections.abc import Iterable
import pandas as pd
import os

class AstGraphGenerator(object):

    def __init__(self, source):
        self.source = source.split("\n")  # lines of the source code
        self.root = ast.parse(source)
        self.current_condition = []
        self.condition_status = []
        self.function_scope = []

    def get_name(self, node):
        return node.__class__.__name__ + "_" + str(hex(int(time_ns())))

    def get_edges(self):
        edges = []
        for f_def_node in ast.iter_child_nodes(self.root):
            if type(f_def_node) == ast.FunctionDef:
                edges.extend(self.parse(f_def_node))
                break # to avoid going through nested definitions

        df = pd.DataFrame(edges)
        return df.astype({col: "Int32" for col in df.columns if col not in {"src", "dst", "type"}})

    def parse(self, node):
        n_type = type(node)
        method_name = "parse_" + n_type.__name__
        if hasattr(self, method_name):
            return self.__getattribute__(method_name)(node)
        else:
            print(type(node))
            print(ast.dump(node))
            print(node._fields)
            pprint(self.source)
            return self.generic_parse(node, node._fields)
            raise Exception()
            # return [type(node)]

    def parse_body(self, nodes):
        edges = []
        last_node = None
        for node in nodes:
            s = self.parse(node)
            if isinstance(s, tuple):
                # some parsers return edges and names. at this level, names are not needed
                edges.extend(s[0])

                if last_node:
                    edges.append({"dst": s[1], "src": last_node, "type": "next"})
                    edges.append({"dst": last_node, "src": s[1], "type": "prev"})

                last_node = s[1]

                for cond_name, cons_stat in zip(self.current_condition, self.condition_status):
                    edges.append({"src": last_node, "dst": cond_name, "type": "depends_on_" + cons_stat})
            else:
                edges.extend(s)
        return edges

    def parse_in_context(self, cond_name, cond_stat, edges, body):
        if isinstance(cond_name, str):
            cond_name = [cond_name]
            cond_stat = [cond_stat]

        for cn, cs in zip(cond_name, cond_stat):
            self.current_condition.append(cn)
            self.condition_status.append(cs)

        edges.extend(self.parse_body(body))

        for i in range(len(cond_name)):
            self.current_condition.pop(-1)
            self.condition_status.pop(-1)

    def parse_as_mention(self, name):
        mention_name = name + "@" + self.function_scope[-1]
        edges = [
            {"src": name, "dst": mention_name, "type": "local_mention"},
            {"src": self.function_scope[-1], "dst": mention_name, "type": "mention_scope"}
        ]
        return edges, mention_name

    def parse_operand(self, node):
        # need to make sure upper level name is correct
        edges = []
        if isinstance(node, str):
            # fall here when parsing attributes, they are given as strings
            iter_ = node
        elif isinstance(node, int) or node is None:
            iter_ = str(node)
        else:
            iter_e = self.parse(node)
            if type(iter_e) == str:
                iter_ = iter_e
            elif type(iter_e) == tuple:
                ext_edges, name = iter_e
                edges.extend(ext_edges)
                iter_ = name
            else:
                # unexpected scenario
                print(node)
                print(ast.dump(node))
                print(iter_e)
                print(type(iter_e))
                pprint(self.source)
                print(self.source[node.lineno - 1].strip())
                raise Exception()

        return iter_, edges

    def parse_and_add_operand(self, node_name, operand, type, edges):

        operand_name, ext_edges = self.parse_operand(operand)
        edges.extend(ext_edges)

        if hasattr(operand, "lineno"):
            edges.append({"src": operand_name, "dst": node_name, "type": type, "line": operand.lineno-1, "end_line": operand.end_lineno-1, "col_offset": operand.col_offset, "end_col_offset": operand.end_col_offset})
        else:
            edges.append({"src": operand_name, "dst": node_name, "type": type})

    def generic_parse(self, node, operands, with_name=None):

        edges = []

        if with_name is None:
            node_name = self.get_name(node)
        else:
            node_name = with_name

        for operand in operands:
            if operand in ["body", "orelse", "finalbody"]:
                self.parse_in_context(node_name, "operand", edges, node.__getattribute__(operand))
            else:
                operand_ = node.__getattribute__(operand)
                if operand_ is not None:
                    if isinstance(operand_, Iterable) and not isinstance(operand_, str):
                        for oper_ in operand_:
                            self.parse_and_add_operand(node_name, oper_, operand, edges)
                    else:
                        self.parse_and_add_operand(node_name, operand_, operand, edges)
                        
        edges.append({"src": node.__class__.__name__, "dst": node_name, "type": "node_type"})

        return edges, node_name

    def parse_type_node(self, node):
        # node.lineno, node.col_offset, node.end_lineno, node.end_col_offset
        if node.lineno == node.end_lineno:
            type_str = self.source[node.lineno][node.col_offset - 1: node.end_col_offset]
            print(type_str)
        else:
            type_str = ""
            for ln in range(node.lineno - 1, node.end_lineno):
                if ln == node.lineno - 1:
                    type_str += self.source[ln][node.col_offset - 1:].strip()
                elif ln == node.end_lineno - 1:
                    type_str += self.source[ln][:node.end_col_offset].strip()
                else:
                    type_str += self.source[ln].strip()
        return type_str

    def parse_FunctionDef(self, node):
        # edges, f_name = self.generic_parse(node, ["name", "args", "returns", "decorator_list"])
        # edges, f_name = self.generic_parse(node, ["args", "returns", "decorator_list"])

        f_name = self.get_name(node)
        self.function_scope.append(f_name)

        edges, f_name = self.generic_parse(node, ["args", "decorator_list"], with_name=f_name)

        if node.returns is not None:
            # returns stores return type annotation
            # can contain quotes
            # https://stackoverflow.com/questions/46458470/should-you-put-quotes-around-type-annotations-in-python
            # https://www.python.org/dev/peps/pep-0484/#forward-references
            annotation = self.source[node.returns.lineno - 1][node.returns.col_offset: node.returns.end_col_offset]
            edges.append({"src": annotation, "dst": f_name, "type": 'returns', "line": node.returns.lineno - 1, "end_line": node.returns.end_lineno - 1, "col_offset": node.returns.col_offset, "end_col_offset": node.returns.end_col_offset})

        assert isinstance(node.name, str)
        edges.append({"src": f_name, "dst": node.name, "type": "fname"})

        # if node.returns:
        #     print(self.source[node.lineno -1]) # can get definition string here

        self.parse_in_context(f_name, "defined_in", edges, node.body)

        self.function_scope.pop(-1)

        return edges

    def parse_AsyncFunctionDef(self, node):
        return self.parse_FunctionDef(node)

    def parse_Assign(self, node):

        edges, assign_name = self.generic_parse(node, ["value", "targets"])

        # for cond_name, cons_stat in zip(self.current_condition, self.condition_status):
        #     edges.append({"src": assign_name, "dst": cond_name, "type": "depends_on_" + cons_stat})

        return edges, assign_name

    def parse_AugAssign(self, node):
        return self.generic_parse(node, ["target", "op", "value"])

    def parse_ClassDef(self, node):
        edges, class_name = self.generic_parse(node, ["name"])

        self.parse_in_context(class_name, "True", edges, node.body)
        return edges, class_name

    def parse_ImportFrom(self, node):
        # similar issues as with parsing alias, module name is parsed as a long chunk
        # print(ast.dump(node))
        edges, name = self.generic_parse(node, ["names"])
        # if node.module:
        #     name_from, edges_from = self.parse_operand(ast.parse(node.module).body[0].value)
        #     edges.extend(edges_from)
        #     edges.append({"src": name_from, "dst": name, "type": "module"})
        return edges, name
        # return self.generic_parse(node, ["module", "names"])

    def parse_Import(self, node):
        return self.generic_parse(node, ["names"])

    def parse_Delete(self, node):
        return self.generic_parse(node, ["targets"])

    def parse_Global(self, node):
        return self.generic_parse(node, ["names"])

    def parse_Nonlocal(self, node):
        return self.generic_parse(node, ["names"])

    def parse_With(self, node):
        edges, with_name = self.generic_parse(node, ["items"])

        self.parse_in_context(with_name, "with", edges, node.body)

        return edges, with_name

    def parse_AsyncWith(self, node):
        return self.parse_With(node)

    def parse_withitem(self, node):
        return self.generic_parse(node, ['context_expr', 'optional_vars'])

    def parse_alias(self, node):
        # TODO
        # aliases should be handled by sourcetrail. here i am trying to assign alias to a
        # local mention of the module. maybe i should simply ignore aliases altogether

        name = self.get_name(node)
        edges = []
        # name, edges = self.parse_operand(ast.parse(node.name).body[0].value) # <- this was the functional line
        # # if node.asname:
        # #     edges.append({"src": name, "dst": node.asname, "type": "alias"})
        return edges, name
        # return self.generic_parse(node, ["name", "asname"])

    def parse_arg(self, node):
        # node.annotation stores type annotation
        # if node.annotation:
        #     print(self.source[node.lineno-1]) # can get definition string here
        #     print(node.arg)

        # # included mention
        name = self.get_name(node)
        edges, mention_name = self.parse_as_mention(node.arg)
        edges.append({'src':mention_name, 'dst': name, 'type': 'arg'})
        # edges, name = self.generic_parse(node, ["arg"])
        if node.annotation is not None:
            # can contain quotes
            # https://stackoverflow.com/questions/46458470/should-you-put-quotes-around-type-annotations-in-python
            # https://www.python.org/dev/peps/pep-0484/#forward-references
            annotation = self.source[node.annotation.lineno - 1][node.annotation.col_offset: node.annotation.end_col_offset]
            edges.append({"src": annotation, "dst": name, "type": 'annotation', "line": node.annotation.lineno-1, "end_line": node.annotation.end_lineno-1, "col_offset": node.annotation.col_offset, "end_col_offset": node.annotation.end_col_offset, "var_line": node.lineno-1, "var_end_line": node.end_lineno-1, "var_col_offset": node.col_offset, "var_end_col_offset": node.end_col_offset})
        return edges, name
        # return self.generic_parse(node, ["arg", "annotation"])

    def parse_AnnAssign(self, node):
        # stores annotation information for variables
        #
        # paths: List[Path] = []
        # AnnAssign(target=Name(id='paths', ctx=Store()), annotation=Subscript(value=Name(id='List', ctx=Load()),
        #           slice=Index(value=Name(id='Path', ctx=Load())),
        #           ctx=Load()), value=List(elts=[], ctx=Load()), simple=1)

        # if node.annotation:
        #     print(self.source[node.lineno-1]) # can get definition string here

        # can contain quotes
        # https://stackoverflow.com/questions/46458470/should-you-put-quotes-around-type-annotations-in-python
        # https://www.python.org/dev/peps/pep-0484/#forward-references
        annotation = self.source[node.lineno - 1][node.annotation.col_offset: node.annotation.end_col_offset]
        edges, name = self.generic_parse(node, ["target"])
        edges.append({"src": annotation, "dst": name, "type": 'annotation', "line": node.annotation.lineno-1, "end_line": node.annotation.end_lineno-1, "col_offset": node.annotation.col_offset, "end_col_offset": node.annotation.end_col_offset, "var_line": node.lineno-1, "var_end_line": node.end_lineno-1, "var_col_offset": node.col_offset, "var_end_col_offset": node.end_col_offset})
        return edges, name
        # return self.generic_parse(node, ["target", "annotation"])

    def parse_Subscript(self, node):
        return self.generic_parse(node, ["value", "slice"])

    def parse_Slice(self, node):
        return self.generic_parse(node, ["lower", "upper", "step"])
    
    def parse_ExtSlice(self, node):
        return self.generic_parse(node, ["dims"])

    def parse_Index(self, node):
        return self.generic_parse(node, ["value"])

    def parse_Lambda(self, node):
        # this is too ambiguous
        edges, lmb_name = self.generic_parse(node, [])
        self.parse_and_add_operand(lmb_name, node.body, "lambda", edges)

        return edges, lmb_name

    def parse_Starred(self, node):
        return self.generic_parse(node, ["value"])

    def parse_Yield(self, node):
        return self.generic_parse(node, ["value"])

    def parse_IfExp(self, node):
        edges, ifexp_name = self.generic_parse(node, ["test"])
        self.parse_and_add_operand(ifexp_name, node.body, "body", edges)
        self.parse_and_add_operand(ifexp_name, node.orelse, "orelse", edges)
        return edges, ifexp_name

    def parse_ExceptHandler(self, node):
        # have missing fields. example:
        # not parsing "name" field
        # except handler is unique for every function
        return self.generic_parse(node, ["type"])

    def parse_Call(self, node):
        return self.generic_parse(node, ["func", "args","keywords"])
        # edges = []
        # # print("\t\t", ast.dump(node))
        # call_name = self.get_name(node)
        # # print(ast.dump(node.func))
        # self.parse_and_add_operand(call_name, node.func, "call_func", edges)
        # # f_name = self.parse(node.func)
        # # call_args = (self.parse(a) for a in node.args)
        # # edges.append({"src": f_name, "dst": call_name, "type": "call_func"})
        # for a in node.args:
        #     self.parse_and_add_operand(call_name, a, "call_arg", edges)
        #     # arg_name, ext_edges = self.parse_operand(a)
        #     # edges.extend(ext_edges)
        #     # edges.append({"src": arg_name, "dst": call_name, "type": "call_arg"})
        # return edges, call_name
        # # return get_call(node.func), tuple(parse(a) for a in node.args)

    def parse_keyword(self, node):
        # change arg name so that it does not mix with variable names
        if isinstance(node.arg, str):
            node.arg += "@keyword"
            return self.generic_parse(node, ["arg", "value"])
        else:
            return self.generic_parse(node, ["value"])

    def parse_name(self, node):
        edges = []
        # if type(node) == ast.Attribute:
        #     left, ext_edges = self.parse(node.value)
        #     right = node.attr
        #     return self.parse(node.value) + "___" + node.attr
        if type(node) == ast.Name:
            return self.parse_as_mention(str(node.id))
        elif type(node) == ast.NameConstant:
            return str(node.value)

    def parse_Attribute(self, node):
        return self.generic_parse(node, ["value", "attr"])

    def parse_Name(self, node):
        return self.parse_name(node)

    def parse_NameConstant(self, node):
        return self.parse_name(node)

    def parse_Constant(self, node):
        # TODO
        # decide whether this name should be unique or not
        name = "Constant_"
        if node.kind is not None:
            name += ""
        return name

    def parse_op_name(self, node):
        return node.__class__.__name__

    def parse_And(self, node):
        return self.parse_op_name(node)
    
    def parse_Or(self, node):
        return self.parse_op_name(node)

    def parse_Not(self, node):
        return self.parse_op_name(node)

    def parse_Is(self, node):
        return self.parse_op_name(node)

    def parse_Gt(self, node):
        return self.parse_op_name(node)

    def parse_Lt(self, node):
        return self.parse_op_name(node)

    def parse_GtE(self, node):
        return self.parse_op_name(node)

    def parse_LtE(self, node):
        return self.parse_op_name(node)

    def parse_Add(self, node):
        return self.parse_op_name(node)

    def parse_Mod(self, node):
        return self.parse_op_name(node)

    def parse_Sub(self, node):
        return self.parse_op_name(node)

    def parse_UAdd(self, node):
        return self.parse_op_name(node)

    def parse_USub(self, node):
        return self.parse_op_name(node)

    def parse_Div(self, node):
        return self.parse_op_name(node)

    def parse_Mult(self, node):
        return self.parse_op_name(node)

    def parse_MatMult(self, node):
        return self.parse_op_name(node)

    def parse_Pow(self, node):
        return self.parse_op_name(node)

    def parse_FloorDiv(self, node):
        return self.parse_op_name(node)
    
    def parse_RShift(self, node):
        return self.parse_op_name(node)

    def parse_LShift(self, node):
        return self.parse_op_name(node)

    def parse_BitXor(self, node):
        return self.parse_op_name(node)

    def parse_BitAnd(self, node):
        return self.parse_op_name(node)

    def parse_BitOr(self, node):
        return self.parse_op_name(node)

    def parse_IsNot(self, node):
        return self.parse_op_name(node)

    def parse_NotIn(self, node):
        return self.parse_op_name(node)

    def parse_In(self, node):
        return self.parse_op_name(node)

    def parse_Invert(self, node):
        return self.parse_op_name(node)

    def parse_Eq(self, node):
        return self.parse_op_name(node)

    def parse_NotEq(self, node):
        return self.parse_op_name(node)

    def parse_Ellipsis(self, node):
        return self.parse_op_name(node)

    def parse_Num(self, node):
        return str(node.n)

    def parse_Str(self, node):
        return self.generic_parse(node, [])
        # return node.s

    def parse_Bytes(self, node):
        return repr(node.s)

    def parse_If(self, node):

        edges, if_name = self.generic_parse(node, ["test"])

        self.parse_in_context(if_name, "True", edges, node.body)
        self.parse_in_context(if_name, "False", edges, node.orelse)

        return edges


    def parse_For(self, node):

        edges, for_name = self.generic_parse(node, ["target", "iter"])
        
        self.parse_in_context(for_name, "for", edges, node.body)
        self.parse_in_context(for_name, "orelse", edges, node.orelse)
        
        return edges #, for_name

    def parse_AsyncFor(self, node):
        return self.parse_For(node)
        
    def parse_Try(self, node):

        edges, try_name = self.generic_parse(node, [])

        self.parse_in_context(try_name, "try", edges, node.body)
        
        for h in node.handlers:
            
            handler_name, ext_edges = self.parse_operand(h)
            edges.extend(ext_edges)
            self.parse_in_context([try_name, handler_name], ["except", "handler"], edges, h.body)
        
        self.parse_in_context(try_name, "final", edges, node.finalbody)
        self.parse_in_context(try_name, "else", edges, node.orelse)
        
        return edges #, try_name   
        
    def parse_While(self, node):

        edges, while_name = self.generic_parse(node, [])
        
        cond_name, ext_edges = self.parse_operand(node.test)
        edges.extend(ext_edges)

        self.parse_in_context([while_name, cond_name], ["while", "True"], edges, node.body)
        
        return edges #, while_name

    def parse_Compare(self, node):
        return self.generic_parse(node, ["left", "ops", "comparators"])

    def parse_BoolOp(self, node):
        return self.generic_parse(node, ["values", "op"])

    def parse_Expr(self, node):
        edges = []
        expr_name, ext_edges = self.parse_operand(node.value)
        edges.extend(ext_edges)
        
        # for cond_name, cons_stat in zip(self.current_condition, self.condition_status):
        #     edges.append({"src": expr_name, "dst": cond_name, "type": "depends_on_" + cons_stat})
        return edges

    def parse_control_flow(self, node):
        edges = []
        call_name = "call" + str(int(time_ns()))
        edges.append({"src": node.__class__.__name__, "dst": call_name, "type": "control_flow"})

        # for cond_name, cons_stat in zip(self.current_condition, self.condition_status):
        #     edges.append({"src": call_name, "dst": cond_name, "type": "depends_on_" + cons_stat})
        return edges, call_name

    def parse_Continue(self, node):
        return self.parse_control_flow(node)

    def parse_Break(self, node):
        return self.parse_control_flow(node)
    
    def parse_Pass(self, node):
        return self.parse_control_flow(node)

    def parse_Assert(self, node):
        return self.generic_parse(node, ["test", "msg"])

    def parse_List(self, node):
        return self.generic_parse(node, ["elts"])

    def parse_Tuple(self, node):
        return self.generic_parse(node, ["elts"])

    def parse_Set(self, node):
        return self.generic_parse(node, ["elts"])

    def parse_Dict(self, node):
        return self.generic_parse(node, ["keys", "values"])

    def parse_UnaryOp(self, node):
        return self.generic_parse(node, ["operand", "op"])

    def parse_BinOp(self, node):
        return self.generic_parse(node, ["left", "right", "op"])

    def parse_Await(self, node):
        return self.generic_parse(node, ["value"])

    def parse_JoinedStr(self, node):
        return self.generic_parse(node, [])
        # return self.generic_parse(node, ["values"])

    def parse_FormattedValue(self, node):
        # have missing fields. example:
        # FormattedValue(value=Subscript(value=Name(id='args', ctx=Load()), slice=Index(value=Num(n=0)), ctx=Load()),conversion=-1, format_spec=None)
        # 'conversion', 'format_spec' not parsed
        return self.generic_parse(node, ["value"])

    def parse_GeneratorExp(self, node):
        return self.generic_parse(node, ["elt", "generators"])

    def parse_ListComp(self, node):
        return self.generic_parse(node, ["elt", "generators"])

    def parse_DictComp(self, node):
        return self.generic_parse(node, ["key", "value", "generators"])

    def parse_SetComp(self, node):
        return self.generic_parse(node, ["elt", "generators"])

    def parse_Return(self, node):
        return self.generic_parse(node, ["value"])

    def parse_Raise(self, node):
        return self.generic_parse(node, ["exc", "cause"])

    def parse_YieldFrom(self, node):
        return self.generic_parse(node, ["value"])

    def parse_arguments(self, node):
        # have missing fields. example:
        #    arguments(args=[arg(arg='self', annotation=None), arg(arg='tqdm_cls', annotation=None), arg(arg='sleep_interval', annotation=None)], vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[])

        # vararg constains type annotations
        return self.generic_parse(node, ["args","vararg"])

    def parse_comprehension(self, node):
        edges = []

        cph_name = "comprehension" + str(int(time_ns()))

        target, ext_edges = self.parse_operand(node.target)
        edges.extend(ext_edges)
        if hasattr(node.target, "lineno"):
            edges.append({"src": target, "dst": cph_name, "type": "target", "line": node.target.lineno-1, "end_line": node.target.end_lineno-1, "col_offset": node.target.col_offset, "end_col_offset": node.target.end_col_offset})
        else:
            edges.append({"src": target, "dst": cph_name, "type": "target"})

        iter_, ext_edges = self.parse_operand(node.iter)
        edges.extend(ext_edges)
        if hasattr(node.iter, "lineno"):
            edges.append({"src": iter_, "dst": cph_name, "type": "iter", "line": node.iter.lineno-1, "end_line": node.iter.end_lineno-1, "col_offset": node.iter.col_offset, "end_col_offset": node.iter.end_col_offset})
        else:
            edges.append({"src": iter_, "dst": cph_name, "type": "iter"})

        for if_ in node.ifs:
            if_n, ext_edges = self.parse_operand(if_)
            edges.extend(ext_edges)
            edges.append({"src": if_n, "dst": cph_name, "type": "ifs"})

        return edges, cph_name

if __name__ == "__main__":
    import sys
    f_bodies = pd.read_csv(sys.argv[1])
    failed = 0
    for ind, c in enumerate(f_bodies['normalized_body']):
        if isinstance(c, str):
            try:
                g = AstGraphGenerator(c.lstrip())
            except SyntaxError as e:
                print(e)
                continue
            failed += 1
            edges = g.get_edges()
            edges.to_csv(os.path.join(os.path.dirname(sys.argv[1]), "body_edges.csv"), mode="a", index=False, header=(ind==0))
            print("\r%d/%d" % (ind, len(f_bodies['normalized_body'])), end = "")
        else:
            print("Skipped not a string")

    print(" " * 30, end="\r")
    print(failed, len(f_bodies['normalized_body']))