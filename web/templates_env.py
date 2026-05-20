import json
import jinja2
from fastapi.templating import Jinja2Templates

_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader("web/templates"),
    autoescape=jinja2.select_autoescape(),
)
_env.filters["fromjson"] = json.loads

templates = Jinja2Templates(env=_env)
