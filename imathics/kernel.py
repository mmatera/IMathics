import sys
import traceback
import logging

from ipykernel.kernelbase import Kernel

from mathics.core.definitions import Definitions
from mathics.core.evaluation import Evaluation, Message, Result
from mathics.core.expression import Integer
from mathics.builtin import builtins
from mathics import settings
from mathics.version import __version__
from mathics.doc.doc import Doc

from IPython.display import Image, SVG
from IPython.display import Latex, HTML,Javascript
import IPython.display as ip_display




class MathicsKernel(Kernel):
    import re 
    svg_open_tag = re.compile('<mtable><mtr><mtd><svg')
    svg_close_tag = re.compile('</svg></mtd></mtr></mtable>')

    implementation = 'Mathics'
    implementation_version = __version__
    language_version = '0.1'    # TODO
    language_info = {
        'name': 'Mathematica',
        'mimetype': 'text/x-mathematica',
    }
    banner = "Mathics kernel"   # TODO
    
    def __init__(self, **kwargs):
        self.mathjax_initialized = False
        Kernel.__init__(self, **kwargs)
        if self.log is None:
            # This occurs if we call as a stand-alone kernel
            # (eg, not as a process)
            # FIXME: take care of input/output, eg StringIO
            #        make work without a session
            self.log = logging.Logger("NotebookApp")

        self.definitions = Definitions(add_builtin=True)        # TODO Cache
        self.definitions.set_ownvalue('$Line', Integer(0))  # Reset the line number


    def do_execute(self, code, silent, store_history=True, user_expressions=None,
                   allow_stdin=False):
        #Initialize mathjax... It should be a beter place to do it inside the imathics kernel
        if not self.mathjax_initialized:
            self.mathjax_initialized = True
            self.Display(Javascript(''' 
               MathJax.Hub.Config({jax: ["input/TeX","input/MathML","input/AsciiMath","output/HTML-CSS","output/NativeMML",
               "output/PreviewHTML"],extensions: ["tex2jax.js","mml2jax.js","asciimath2jax.js","MathMenu.js","MathZoom.js",
               "fast-preview.js", "AssistiveMML.js"],TeX: { extensions: ["AMSmath.js","AMSsymbols.js","noErrors.js",
               "noUndefined.js"]}});''',
                                    lib="https://cdn.mathjax.org/mathjax/latest/MathJax.js"))
        # TODO update user definitions

        response = {
            'payload': [],
            'user_expressions': {},
        }

        try:
            evaluation = Evaluation(code, self.definitions, out_callback=self.out_callback,
                                    timeout=settings.TIMEOUT,format="xml")
        except Exception as exc:
            response['status'] = 'error'
            response['ename'] = 'System:exception'
            response['traceback'] = traceback.format_exception(*sys.exc_info())
            evaluation = Evaluation()
            raise exc
        else:
            response['status'] = 'ok'

        if not silent:
            for result in evaluation.results:
                if result.result is not None:
                    xmlchain = result.result
                    xmlchain= MathicsKernel.svg_open_tag.sub("<mtable><mtr><mtd><annotation-xml encoding=\"text/html\" ><svg",xmlchain)
                    xmlchain= MathicsKernel.svg_close_tag.sub("</svg></annotation-xml></mtd></mtr></mtable>",xmlchain)
                    data = {
                        'text/html': xmlchain,
                        # TODO html / mathjax output
                    }
                    
                    content = {'execution_count': result.line_no, 'data': data, 'metadata': {}}
                    self.send_response(self.iopub_socket, 'execute_result', content)

        response['execution_count'] = self.definitions.get_line()

        return response

    def out_callback(self, out):
        if out.is_message:
            content = {
                'name': 'stderr',
                'text': '{symbol}::{tag}: {text}\n'.format(**out.get_data()),
            }
        elif out.is_print:
            content = {
                'name': 'stdout',
                'text': out.text + '\n',
            }
        else:
            raise ValueError('Unknown out')
        self.send_response(self.iopub_socket, 'stream', content)

    def do_inspect(self, code, cursor_pos, detail_level=0):
        # name = code[:cursor_pos]
        name = code

        if '`' not in name:
            name = 'System`' + name

        try:
            instance = builtins[name]
        except KeyError:
            return {'status': 'ok', 'found': False, 'data': {}, 'metadata': {}}

        doc = Doc(instance.__doc__ or '')    # TODO Handle possible ValueError here
        data = {'text/plain': doc.text(detail_level), 'text/html': doc.html()}        # TODO 'application/x-tex': doc.latex()
        return {'status': 'ok', 'found': True, 'data': data, 'metadata': {}}

    @staticmethod
    def do_is_complete(code):
        code = code.rstrip()

        trailing_ops = ['+', '-', '/', '*', '^', '=', '>', '<', '/;', '/:',
                        '/.', '&&', '||']
        if any(code.endswith(op) for op in trailing_ops):
            return {'status': 'incomplete', 'indent': ''}

        brackets = [('(', ')'), ('[', ']'), ('{', '}')]
        kStart, kEnd, stack = 0, 1, []
        in_string = False
        for char in code:
            if char == '"':
                in_string = not in_string
            if not in_string:
                for bracketPair in brackets:
                    if char == bracketPair[kStart]:
                        stack.append(char)
                    elif char == bracketPair[kEnd]:
                        if len(stack) == 0:
                            return {'status': 'invalid'}
                        if stack.pop() != bracketPair[kStart]:
                            return {'status': 'invalid'}
        if in_string:
            return {'status': 'incomplete', 'indent': ''}
        elif len(stack) != 0:
            return {'status': 'incomplete', 'indent': 4 * len(stack) * ' '}
        else:
            return {'status': 'complete'}


#Borrowed from metakernel package    
    def repr(self, item):
        return repr(item)

#Borrowed from metakernel package    
    def Display(self, *args, **kwargs):
        clear_output = kwargs.get("clear_output", False)
        for message in args:
            if isinstance(message, HTML):
                if clear_output:
                    self.send_response(self.iopub_socket, 'clear_output',
                                       {'wait': True})
            # if Widget and isinstance(message, Widget):
            #     self.log.debug('Display Widget')
            #     self._ipy_formatter(message)
            else:
                self.log.debug('Display Data')
                try:
                    data = _formatter(message, self.repr)
                except Exception as e:
                    self.Error(e)
                    return
                self.send_response(self.iopub_socket, 'display_data',
                                   {'data': data,
                                    'metadata': dict()})

#Borrowed from metakernel package    
def _formatter(data, repr_func):
    reprs = {}
    reprs['text/plain'] = repr_func(data)

    lut = [("_repr_png_", "image/png"),
           ("_repr_jpeg_", "image/jpeg"),
           ("_repr_html_", "text/html"),
           ("_repr_markdown_", "text/markdown"),
           ("_repr_svg_", "image/svg+xml"),
           ("_repr_latex_", "text/latex"),
           ("_repr_json_", "application/json"),
           ("_repr_javascript_", "application/javascript"),
           ("_repr_pdf_", "application/pdf")]

    for (attr, mimetype) in lut:
        obj = getattr(data, attr, None)
        if obj:
            reprs[mimetype] = obj

    retval = {}
    for (mimetype, value) in reprs.items():
        try:
            value = value()
        except Exception:
            pass
        if not value:
            continue
        if isinstance(value, bytes):
            try:
                value = value.decode('utf-8')
            except Exception:
                value = base64.encodestring(value)
                value = value.decode('utf-8')
        try:
            retval[mimetype] = str(value)
        except:
            retval[mimetype] = value
    return retval
