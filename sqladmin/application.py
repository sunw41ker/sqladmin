from os import remove
from typing import TYPE_CHECKING, List, Optional, OrderedDict, Type, Union, Any

from jinja2 import ChoiceLoader, FileSystemLoader, PackageLoader
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from sqladmin.backends.relationships import BaseRelationshipsLoader
from sqladmin.backends import get_used_backend, BackendEnum
import starlette

used_backend = get_used_backend()

if used_backend == BackendEnum.SA_14:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession  # type: ignore
    Gino = None
    EngineTypeTuple = Engine, AsyncEngine
    EngineType = Union[Engine, AsyncEngine]
elif used_backend == BackendEnum.GINO:
    from sqladmin.backends.gino.models import fetch_all_relationships
    from gino.ext.starlette import Gino, GinoEngine  # type: ignore
    AsyncEngine, AsyncSession = None, None 
    EngineTypeTuple = (Gino, ) 
    EngineType = Gino

from sqladmin.forms import prepare_endpoint_form_display

from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

if TYPE_CHECKING:
    from sqladmin.models import ModelAdmin


__all__ = [
    "Admin",
]


class BaseAdmin:
    """Base class for implementing Admin interface.

    Danger:
        This class should almost never be used directly.
    """

    def __init__(
        self,
        app: Starlette,
        engine: EngineType,
        base_url: str = "/admin",
        title: str = "Admin",
        logo_url: str = None,
        relationships_loader: BaseRelationshipsLoader = None,
        # base_model: Any = None,
    ) -> None:
        self.app = app
        self.engine = engine
        self.backend = used_backend
        self.base_url = base_url
        # if used_backend == BackendEnum.GINO:
        #     self.relationships_loader = relationships_loader or BaseModelRelationshipsLoader(base_model=base_model)
        # else:
        #     self.relationships_loader = relationships_loader
        self.relationships_loader = relationships_loader
        self._model_admins: List["ModelAdmin"] = []

        self.templates = Jinja2Templates("templates/sqladmin")
        self.templates.env.loader = ChoiceLoader(
            [
                FileSystemLoader("templates/sqladmin"),
                PackageLoader("sqladmin", "templates/sqladmin"),
            ]
        )
        self.templates.env.globals["min"] = min
        self.templates.env.globals["admin_title"] = title
        self.templates.env.globals["admin_logo_url"] = logo_url
        self.templates.env.globals["model_admins"] = self.model_admins

    @property
    def model_admins(self) -> List["ModelAdmin"]:
        """Get list of ModelAdmins lazily.

        Returns:
            List of ModelAdmin classes registered in Admin.
        """

        return self._model_admins

    def _find_model_admin(self, identity: str) -> "ModelAdmin":
        for model_admin in self.model_admins:  # empty mdeladmins, todo: check admin fixtures
            if model_admin.identity == identity:
                return model_admin

        raise HTTPException(status_code=404)

    def register_model(self, model: Type["ModelAdmin"]) -> None:
        """Register ModelAdmin to the Admin.

        Args:
            model: ModelAdmin class to register in Admin.

        ???+ usage
            ```python
            from sqladmin import Admin, ModelAdmin

            class UserAdmin(ModelAdmin, model=User):
                pass

            admin.register_model(UserAdmin)
            ```
        """

        # Set database engine from Admin instance
        model.engine = self.engine
        model.backend = self.backend
        model.relationships_loader = self.relationships_loader
        if self.backend in (BackendEnum.SA_13, BackendEnum.SA_14, ):
            if isinstance(model.engine, Engine):
                model.sessionmaker = sessionmaker(bind=model.engine, class_=Session)
                model.async_engine = False
            else:
                model.sessionmaker = sessionmaker(bind=model.engine, class_=AsyncSession)
                model.async_engine = True

        self._model_admins.append(model())

    def unregister_model(self, model: Type["ModelAdmin"]) -> bool:
        for ma in self._model_admins:
            if isinstance(ma, model):
                self._model_admins.remove(ma)
                return True
        return False


class BaseAdminView(BaseAdmin):
    async def _list(self, request: Request) -> None:
        model_admin = self._find_model_admin(request.path_params["identity"])
        if not model_admin.is_accessible(request):
            raise HTTPException(status_code=403)

    async def _create(self, request: Request) -> None:
        model_admin = self._find_model_admin(request.path_params["identity"])
        if not model_admin.can_create or not model_admin.is_accessible(request):
            raise HTTPException(status_code=403)

    async def _details(self, request: Request) -> None:
        model_admin = self._find_model_admin(request.path_params["identity"])
        if not model_admin.can_view_details or not model_admin.is_accessible(request):
            raise HTTPException(status_code=403)

    async def _delete(self, request: Request) -> None:
        model_admin = self._find_model_admin(request.path_params["identity"])
        if not model_admin.can_delete or not model_admin.is_accessible(request):
            raise HTTPException(status_code=403)

    async def _edit(self, request: Request) -> None:
        model_admin = self._find_model_admin(request.path_params["identity"])
        if not model_admin.can_edit or not model_admin.is_accessible(request):
            raise HTTPException(status_code=403)


class Admin(BaseAdminView):
    """Main entrypoint to admin interface.

    ???+ usage
        ```python
        from fastapi import FastAPI
        from sqladmin import Admin, ModelAdmin

        from mymodels import User # SQLAlchemy model


        app = FastAPI()
        admin = Admin(app, engine)


        class UserAdmin(ModelAdmin, model=User):
            column_list = [User.id, User.name]


        admin.register_model(UserAdmin)
        ```
    """

    def __init__(
        self,
        app: Starlette,
        engine: EngineType,
        base_url: str = "/admin",
        title: str = "Admin",
        logo_url: str = None,
        relationships_loader: BaseRelationshipsLoader = None
    ) -> None:
        """
        Args:
            app: Starlette or FastAPI application.
            engine: SQLAlchemy engine instance.
            base_url: Base URL for Admin interface.
            title: Admin title.
            logo_url: URL of logo to be displayed instead of title.
        """
        # app_state = app.state 
        root_app = app
        assert isinstance(engine, EngineTypeTuple)
        super().__init__(
            app=app, engine=engine, base_url=base_url, title=title, logo_url=logo_url,
            relationships_loader=relationships_loader
        )

        statics = StaticFiles(packages=["sqladmin"])

        def http_exception(request: Request, exc: Exception) -> Response:
            assert isinstance(exc, HTTPException)
            context = {
                "request": request,
                "status_code": exc.status_code,
                "message": exc.detail,
            }
            return self.templates.TemplateResponse(
                "error.html", context, status_code=exc.status_code
            )

        admin = Starlette(
            routes=[
                Mount("/statics", app=statics, name="statics"),
                Route("/", endpoint=self.index, name="index"),
                Route("/{identity}/list", endpoint=self.list, name="list"),
                Route(
                    "/{identity}/details/{pk}", endpoint=self.details, name="details"
                ),
                Route(
                    "/{identity}/delete/{pk}",
                    endpoint=self.delete,
                    name="delete",
                    methods=["DELETE"],
                ),
                Route(
                    "/{identity}/create",
                    endpoint=self.create,
                    name="create",
                    methods=["GET", "POST"],
                ),
                Route(
                    "/{identity}/edit/{pk}",
                    endpoint=self.edit,
                    name="edit",
                    methods=["GET", "POST"],
                ),
            ],
            exception_handlers={HTTPException: http_exception},
        )
        # app.include_router(
        #     api_router,
        #     prefix=f"{settings.LATEST_API_VERSION}/{APP_NAME}",
        #     tags=[APP_NAME],
        # )
        # app.include_router(view_router)
        admin.state.root = self.app.state
        self.app.mount(base_url, app=admin, name="admin")
        # self.app.state
        

    async def index(self, request: Request) -> Response:
        """Index route which can be overriden to create dashboards."""
        return self.templates.TemplateResponse("index.html", {"request": request})

    async def list(self, request: Request) -> Response:
        """List route to display paginated Model instances."""

        await self._list(request)

        model_admin = self._find_model_admin(request.path_params["identity"])

        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 0))

        model_admin.update_params(request)
        pagination = await model_admin.list(page, page_size)
        pagination.add_pagination_urls(request.url)
        
        list_columns_display = [
            {
                **(await model_admin.get_list_col_head_display(lc)),
                'admin': lc, 
            }
            for lc in model_admin.columns.all()
        ]
        
        context = {
            "request": request,
            "model_admin": model_admin,
            "pagination": pagination,
            "list_columns_display": list_columns_display
        }

        return self.templates.TemplateResponse(model_admin.list_template, context)

    async def details(self, request: Request) -> Response:
        """Details route."""

        await self._details(request)

        model_admin = self._find_model_admin(request.path_params["identity"])
        
        # pk = request.path_params["pk"]
        # if not isinstance(pk, model_admin.pk_column.type.python_type):
        #     pk = model_admin.pk_column.type.python_type(pk)
        model = await model_admin.get_model_by_pk(request.path_params["pk"])
        if not model:
            raise HTTPException(status_code=404)

        context = {
            "request": request,
            "model_admin": model_admin,
            "model": model,
            "title": model_admin.name,
        }

        return self.templates.TemplateResponse(model_admin.details_template, context)

    async def delete(self, request: Request) -> Response:
        """Delete route."""

        await self._delete(request)

        identity = request.path_params["identity"]
        model_admin = self._find_model_admin(identity)

        model = await model_admin.get_model_by_pk(request.path_params["pk"])
        if not model:
            raise HTTPException(status_code=404)

        await model_admin.delete_model(model)

        return Response(content=request.url_for("admin:list", identity=identity))

    async def create(self, request: Request) -> Response:
        """Create model endpoint."""

        await self._create(request)

        identity = request.path_params["identity"]
        model_admin = self._find_model_admin(identity)

        Form = await model_admin.scaffold_form()
        starlette_form = await request.form()
        form = Form(starlette_form)

        context = {
            "request": request,
            "model_admin": model_admin,
            "form": form,
        }

        if request.method == "GET":
            context["form"] = await self._prepare_endpoint_form(context["form"], self.create.__name__, request)
            return self.templates.TemplateResponse(model_admin.create_template, context)

        if not form.validate():
            context["form"] = await self._prepare_endpoint_form(context["form"], self.create.__name__, request)
            return self.templates.TemplateResponse(
                model_admin.create_template,
                context,
                status_code=400,
            )

        model = await model_admin.init_model_instance( 
            data=form.data, 
            starlette_form=starlette_form,
            request=request,
            form=form,
        )    
        await model_admin.insert_model(model)

        return RedirectResponse(
            request.url_for("admin:list", identity=identity),
            status_code=302,
        )
    
    async def edit(self, request: Request) -> Response:
        """Edit model endpoint."""

        await self._edit(request)

        identity = request.path_params["identity"]
        model_admin = self._find_model_admin(identity)

        model = await model_admin.get_model_by_pk(request.path_params["pk"])
        if not model:
            raise HTTPException(status_code=404)

        Form = await model_admin.scaffold_form()
        context = await model_admin.get_edit_context({
            "request": request,
            "model_admin": model_admin,
        }, model=model, identity=identity, app=self.app)

        if request.method == "GET":
            if used_backend == BackendEnum.GINO:
                await fetch_all_relationships(model)
            context["form"] = Form(obj=model)
            context["form"] = await self._prepare_endpoint_form(context["form"], self.edit.__name__, request)
            return self.templates.TemplateResponse(model_admin.edit_template, context)

        starlette_form = await request.form()
        form = Form(starlette_form)
        if not form.validate(schema=model_admin.schema):
            context["form"] = await self._prepare_endpoint_form(form, self.edit.__name__, request)
            return self.templates.TemplateResponse(
                model_admin.edit_template,
                context,
                status_code=400,
            )

        data = await model_admin.prepare_update_data(
            pk=request.path_params["pk"], 
            data=form.data, 
            starlette_form=starlette_form,
            request=request,
            form=form,
        )
        await model_admin.update_model(pk=request.path_params["pk"], data=data)
    
        return RedirectResponse(
            request.url_for("admin:list", identity=identity),
            status_code=302,
        )

    async def _prepare_endpoint_form(self, form, endpoint: str, request: Request):
        return await prepare_endpoint_form_display(form, endpoint)
