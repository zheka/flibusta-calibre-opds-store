# -*- coding: utf-8 -*-

from __future__ import (unicode_literals, division, absolute_import, print_function)

__license__ = 'GPL 3'
__copyright__ = '2012, Sergey Kuznetsov <clk824@gmail.com>, 2022, Ed Ryzhov <ed.ryzhov@gmail.com>'
__docformat__ = 'restructuredtext en'

from contextlib import closing
from qt.core import QUrl
from calibre import (browser, guess_extension)
from calibre.gui2 import open_url
from calibre.utils.xml_parse import safe_xml_fromstring
from calibre.gui2.store import StorePlugin
from calibre.gui2.store.search_result import SearchResult
from calibre.gui2.store.web_store_dialog import WebStoreDialog
from calibre.utils.opensearch.description import Description
from calibre.utils.opensearch.query import Query
from calibre.gui2.store.search_result import SearchResult

class _Catalog:

    def __init__(self, **args):
        self._name = args.get('name')
        self._web_url = args.get('web_url')
        self._open_search_url = args.get('open_search_url')
        self._search_url_template = args.get('search_url_template')

    def name(self):
        return self._name

    def web_url(self):
        return self._web_url

    def link(self, href):
        if href.startswith('/'):
            return self._web_url + href
        return href

    def search_url_template(self):
        if not self._search_url_template:
            d = Description(self._open_search_url)
            self._search_url_template = d.get_best_template()
            print('{name} search url template: {url}'.format(name=self._name, url=self._search_url_template))
        return self._search_url_template


class FlibustaStore(StorePlugin):

    my_catalog = _Catalog(
        name='Flibusta',
        web_url='https://flibusta.is',
        open_search_url='https://flibusta.is/opds-opensearch.xml')

    #my_catalog = _Catalog(
    #    name='Coollib',
    #    web_url='https://coollib.net',
    #    open_search_url='https://coollib.cc/opds-opensearch.xml',
    #    search_url_template='http://coollib.net/opds/search?searchTerm={searchTerms}&searchType=books&pageNumber={startPage?}')

    def open(self, parent=None, detail_item=None, external=False):
        if not hasattr(self, 'web_url'):
            return

        if external or self.config.get('open_external', False):
            open_url(QUrl(detail_item if detail_item else self.web_url))
        else:
            d = WebStoreDialog(self.gui, self.web_url, parent, detail_item, create_browser=self.create_browser)
            d.setWindowTitle(self.name)
            d.set_tags(self.config.get('tags', ''))
            d.exec()

    def search(self, query, max_results=10, timeout=60):
        yield from FlibustaStore.open_search(FlibustaStore.my_catalog, query, max_results, timeout)

    def open_search(catalog, query, max_results, timeout):
        url_template = catalog.search_url_template()
        if not url_template:
            return

        # set up initial values
        oquery = Query(url_template)
        oquery.searchTerms = query
        oquery.count = max_results
        url = oquery.url()

        print('{name} search: {url}'.format(name=catalog.name(), url=url))

        counter = max_results
        br = browser()
        with closing(br.open(url, timeout=timeout)) as f:
            content = f.read()
            doc = safe_xml_fromstring(content)

            for data in doc.xpath('//*[local-name() = "entry"]'):
                if counter <= 0:
                    break
                counter -= 1

                s = SearchResult()
                s.detail_item = ''.join(data.xpath('./*[local-name() = "id"]/text()')).strip()

                for link in data.xpath('./*[local-name() = "link"]'):
                    rel = link.get('rel')
                    href = link.get('href')
                    type = link.get('type')

                    if rel and href and type:
                        if 'http://opds-spec.org/thumbnail' in rel:
                            s.cover_url = catalog.link(href)
                        elif 'http://opds-spec.org/image/thumbnail' in rel:
                            s.cover_url = catalog.link(href)
                        elif 'http://opds-spec.org/acquisition/buy' in rel:
                            s.detail_item = catalog.link(href)
                        elif 'http://opds-spec.org/acquisition/sample' in rel:
                            pass
                        elif 'alternate' in rel:
                            s.detail_item = catalog.link(href)
                        elif 'http://opds-spec.org/acquisition' in rel:
                            if type:
                                ext = FlibustaStore.custom_guess_extension(type)
                                if ext:
                                    s.downloads[ext] = catalog.link(href)

                s.formats = ', '.join(s.downloads.keys()).strip()

                s.title = ' '.join(data.xpath('./*[local-name() = "title"]//text()')).strip()
                s.author = ', '.join(data.xpath('./*[local-name() = "author"]//*[local-name() = "name"]//text()')).strip()
                s.price = '$0.00'
                s.drm = SearchResult.DRM_UNLOCKED

                print('  {author} - {title}'.format(author=s.author, title=s.title))
                for ext, url in s.downloads.items():
                    print('    {ext}: {url}'.format(ext=ext, url=url))

                yield s

    def custom_guess_extension(type):
        ext = guess_extension(type)
        if ext:
            return ext[1:].upper().strip()
        elif 'application/fb2' in type:
            return 'FB2'
        elif 'application/epub' in type:
            return 'EPUB'
        elif 'application/x-mobipocket-ebook' in type:
            return 'MOBI'
        else:
            return None
