from __future__ import annotations
import logging
import shutil
import typing
from typing import Optional, List, Set, Union, Callable
import typing_extensions

from .element import Element

if typing_extensions.TYPE_CHECKING:
    from .browser import Browser, PathLike
from .config import Config
from .. import cdp

__registered__instances__: Set[Browser] = set()

logger = logging.getLogger(__name__)
T = typing.TypeVar("T")


async def start(
    user_data_dir: Optional[PathLike] = None,
    headless: Optional[bool] = False,
    browser_executable_path: Optional[PathLike] = None,
    browser_args: Optional[List[str]] = None,
    sandbox: Optional[bool] = True,
    lang: Optional[str] = None,
    **kwargs: Optional[dict],
) -> Browser:
    """
    helper function to launch a browser. it accepts several keyword parameters.
    conveniently, you can just call it bare (no parameters) to quickly launch an instance
    with best practice defaults.
    note: this should be called ```await start()```

    :param user_data_dir:
    :type user_data_dir: PathLike

    :param headless:
    :type headless: bool

    :param browser_executable_path:
    :type browser_executable_path: PathLike

    :param browser_args: ["--some-chromeparam=somevalue", "some-other-param=someval"]
    :type browser_args: List[str]

    :param sandbox: default True, but when set to False it adds --no-sandbox to the params, also
    when using linux under a root user, it adds False automatically (else chrome won't start
    :type sandbox: bool

    :param lang: language string
    :type lang: str
    :return:
    """

    config = Config(
        user_data_dir,
        headless,
        browser_executable_path,
        browser_args,
        sandbox,
        lang,
        **kwargs,
    )
    from .browser import Browser

    return await Browser.create(config)


def get_registered_instances():
    return __registered__instances__


def free_port() -> int:
    """
    Determines a free port using sockets.
    """
    import socket

    free_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    free_socket.bind(("127.0.0.1", 0))
    free_socket.listen(5)
    port: int = free_socket.getsockname()[1]
    free_socket.close()
    return port


def deconstruct_browser():
    import time

    for _ in __registered__instances__:
        if not _.stopped:
            _.stop()
        for attempt in range(5):
            try:
                if _.config and not _.config.custom_data_dir:
                    shutil.rmtree(_.config.user_data_dir, ignore_errors=False)
            except FileNotFoundError as e:
                break
            except (PermissionError, OSError) as e:
                if attempt == 4:
                    logger.debug(
                        "problem removing data dir %s\nConsider checking whether it's there and remove it by hand\nerror: %s",
                        _.config.user_data_dir,
                        e,
                    )
                    break
                time.sleep(0.15)
                continue
        logger.info("successfully removed temp profile %s", _.config.user_data_dir)


class Meta(type):
    REGISTRY = {}

    def __new__(mcls, name, bases, attrs):
        # instantiate a new type corresponding to the type of class being defined
        # this is currently RegisterBase but in child classes will be the child class
        instance = super().__new__(mcls, name, bases, attrs)
        mcls.REGISTRY[instance.__name__] = instance
        return instance

    def __init__(cls, name, bases, attrs):
        super().__init__(name, bases, attrs)

    def __call__(self, *args, **kwargs):
        instance = super().__call__(*args, **kwargs)
        instance.get_registry = self.get_registry
        type(self).REGISTRY[type(instance).__name__] = instance
        return instance

    def __del__(cls):
        print(" meta __del__")

    @classmethod
    def get_registry(cls):
        return dict(cls.REGISTRY)


#
# def flatten(node: cdp.dom.Node):
#     """returns a flat list of dom nodes from a hierarchical structured node"""
#
#     def _flatten(node: cdp.dom.Node, __d=0):
#         if node.children:
#             for c in node.children:
#                 yield from _flatten(c, __d + 1)
#                 continue
#         else:
#             yield node
#
#     return list(_flatten(node))

#
# def find_recurse(doc: cdp.dom.Node, node_id: cdp.dom.NodeId):
#
#     if doc.children:
#         for child in doc.children:
#             if child.node_id == node_id:
#                 return child
#             result = find_recurse(child, node_id)
#             if result:
#                 return result


def filter_recurse_all(
    doc: T, predicate: Callable[[cdp.dom.Node, Element], bool]
) -> List[T]:
    """
    test each child using predicate(child), and return all children for which predicate(child) == True

    :param doc: the cdp.dom.Node object or :py:class:`nodriver.Element`
    :param predicate: a function which takes a node as first parameter and returns a boolean, where True means include
    :return:
    :rtype:
    """
    if not hasattr(doc, "children"):
        raise TypeError("object should have a .children attribute")
    out = []
    if doc and doc.children:
        for child in doc.children:
            if predicate(child):
                # if predicate is True
                out.append(child)
            out.extend(filter_recurse_all(child, predicate))
            # if result:
            #     out.append(result)
    return out


def filter_recurse(doc: T, predicate: Callable[[cdp.dom.Node, Element], bool]) -> T:
    """
    test each child using predicate(child), and return the first child of which predicate(child) == True

    :param doc: the cdp.dom.Node object or :py:class:`nodriver.Element`
    :param predicate: a function which takes a node as first parameter and returns a boolean, where True means include

    """
    if not hasattr(doc, "children"):
        raise TypeError("object should have a .children attribute")

    if doc and doc.children:
        for child in doc.children:
            if predicate(child):
                # if predicate is True
                return child
            result = filter_recurse(child, predicate)
            if result:
                return result


def remove_from_tree(tree: cdp.dom.Node, node: cdp.dom.Node) -> cdp.dom.Node:
    if not hasattr(tree, "children"):
        raise TypeError("object should have a .children attribute")

    if tree and tree.children:
        for child in tree.children:
            if child.backend_node_id == node.backend_node_id:
                tree.children.remove(child)
            remove_from_tree(child, node)
    return tree


async def html_from_tree(tree: Union[cdp.dom.Node, Element], target: "nodriver.Target"):
    if not hasattr(tree, "children"):
        raise TypeError("object should have a .children attribute")
    out = ""
    if tree and tree.children:
        for child in tree.children:
            if isinstance(child, Element):
                out += await child.get_html()
            else:
                out += await target.send(
                    cdp.dom.get_outer_html(backend_node_id=child.backend_node_id)
                )
            out += await html_from_tree(child, target)
    return out
