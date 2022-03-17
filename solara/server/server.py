import os
import sys
import traceback
from pathlib import Path
from typing import Optional
from uuid import uuid4

import ipywidgets as widgets
import jinja2
import react_ipywidgets
from jupyter_core.paths import jupyter_config_path, jupyter_path
from jupyter_server.services.config import ConfigManager
from react_ipywidgets.core import Element, render

from . import app
from .app import AppContext, AppScript
from .kernel import BytesWrap, Kernel, WebsocketStreamWrapper

# templates = Jinja2Templates(directory=str(directory / "templates"))
directory = Path(__file__).parent
template_name = "vuetify.html"

jinja_loader = jinja2.FileSystemLoader(str(directory / "templates"))
jinja_env = jinja2.Environment(loader=jinja_loader, autoescape=True)
solara_app = AppScript(os.environ.get("SOLARA_APP", "solara.examples:app"))


def run_app():
    main_object = solara_app.run()

    if isinstance(main_object, widgets.Widget):
        return main_object
    elif isinstance(main_object, Element):
        # container = widgets.VBox()
        import ipyvuetify

        container = ipyvuetify.Html(tag="div", style_="display: flex; flex: 0 1 auto; align-items: left; justify-content: left")
        # container = ipyvuetify.Html(tag="div")
        render(main_object, container, handle_error=False)
        return container
    else:
        raise ValueError(f"Main object (with name {solara_app.app_name} in {solara_app.path}) is not a Widget or Element, but {type(main_object)}")


async def read_root(context_id: Optional[str]):
    print("root", context_id)
    # context_id = None
    if context_id is None or context_id not in app.contexts:
        kernel = Kernel()
        context_id = str(uuid4())
        context = app.contexts[context_id] = AppContext(kernel=kernel, control_sockets=[], widgets={})
        with context:
            widgets.register_comm_target(kernel)
            assert kernel is Kernel.instance()
        try:
            with context:
                widget = run_app()
        except react_ipywidgets.core.ComponentCreateError as e:
            from rich.console import Console

            console = Console(record=True)
            console.print(e.rich_traceback)
            error = console.export_html()
            widget = widgets.HTML(f"<pre>{error}</pre>")
            # raise
        except Exception as e:
            error = ""
            error = "".join(traceback.format_exception(None, e, e.__traceback__))
            print(error, file=sys.stdout, flush=True)
            # widget = widgets.Label(value="Error, see server logs")
            import html

            error = html.escape(error)
            with context:
                widget = widgets.HTML(f"<pre>{error}</pre>")
            # raise
        context.widgets["content"] = widget
    else:
        context = app.contexts[context_id]

    model_id = context.widgets["content"].model_id

    read_config_path = [os.path.join(p, "serverconfig") for p in jupyter_config_path()]
    read_config_path += [os.path.join(p, "nbconfig") for p in jupyter_config_path()]
    config_manager = ConfigManager(read_config_path=read_config_path)
    enable_nbextensions = True
    if enable_nbextensions:
        notebook_config = config_manager.get("notebook")
        # except for the widget extension itself, since Voilà has its own
        load_extensions = notebook_config.get("load_extensions", {})
        if "jupyter-js-widgets/extension" in load_extensions:
            load_extensions["jupyter-js-widgets/extension"] = False
        if "voila/extension" in load_extensions:
            load_extensions["voila/extension"] = False
        # print(load_extensions.items())
        ignorelist = [
            "jupytext/index",
            "nbextensions_configurator/config_menu/main",
            "jupytext/index",
            "nbdime/index",
            "voila/extension",
            "contrib_nbextensions_help_item/main",
            "execute_time/ExecuteTime",
        ]
        nbextensions = [name for name, enabled in load_extensions.items() if enabled and name not in ignorelist]
    else:
        nbextensions = []

    base_url = "/"
    resources = {
        "theme": "light",
        "nbextensions": nbextensions,
    }
    template: jinja2.Template = jinja_env.get_template(template_name)
    response = template.render(**{"model_id": model_id, "base_url": base_url, "resources": resources})
    return response, context_id


def nbext(dir, filename):
    """The path to look for Javascript notebook extensions"""
    paths = jupyter_path("nbextensions")
    # FIXME: remove IPython nbextensions path after a migration period
    try:
        from IPython.paths import get_ipython_dir
    except ImportError:
        pass
    else:
        paths.append(os.path.join(get_ipython_dir(), "nbextensions"))
    for path in paths:
        p = Path(path) / dir / filename
        if p.exists():
            with open(p) as f:
                data = f.read()
            return data