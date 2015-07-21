from __future__ import unicode_literals
from future.builtins import str

from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse, Http404
from django.shortcuts import get_object_or_404
from django.contrib import messages

from mezzanine.pages.models import Page, PageMoveException
from mezzanine.utils.urls import home_slug
from mezzanine.utils.views import render,paginate

from mezzanine.conf import settings


from mezzanine.blog.models import BlogPost,BlogCategory


@staff_member_required
def admin_page_ordering(request):
    """
    Updates the ordering of pages via AJAX from within the admin.
    """

    def get_id(s):
        s = s.split("_")[-1]
        return int(s) if s.isdigit() else None
    page = get_object_or_404(Page, id=get_id(request.POST['id']))
    old_parent_id = page.parent_id
    new_parent_id = get_id(request.POST['parent_id'])
    new_parent = Page.objects.get(id=new_parent_id) if new_parent_id else None

    try:
        page.get_content_model().can_move(request, new_parent)
    except PageMoveException as e:
        messages.error(request, e)
        return HttpResponse('error')

    # Perform the page move
    if new_parent_id != page.parent_id:
        # Parent changed - set the new parent and re-order the
        # previous siblings.
        page.set_parent(new_parent)
        pages = Page.objects.filter(parent_id=old_parent_id)
        for i, page in enumerate(pages.order_by('_order')):
            Page.objects.filter(id=page.id).update(_order=i)
    # Set the new order for the moved page and its current siblings.
    for i, page_id in enumerate(request.POST.getlist('siblings[]')):
        Page.objects.filter(id=get_id(page_id)).update(_order=i)

    return HttpResponse("ok")

def getposts(request, tag=None, year=None, month=None, username=None,
                   category=None, template="blog/blog_post_list.html",
                   extra_context=None):
    
    blog_posts = BlogPost.objects.published(for_user=request.user)
    if tag is not None:
        tag = get_object_or_404(Keyword, slug=tag)
        blog_posts = blog_posts.filter(keywords__keyword=tag)
    if year is not None:
        blog_posts = blog_posts.filter(publish_date__year=year)
        if month is not None:
            blog_posts = blog_posts.filter(publish_date__month=month)
            try:
                month = month_name[int(month)]
            except IndexError:
                raise Http404()
    if category is not None:
        category = get_object_or_404(BlogCategory, slug=category)
        blog_posts = blog_posts.filter(categories=category)

    author = None
    if username is not None:
        author = get_object_or_404(User, username=username)
        blog_posts = blog_posts.filter(user=author)

    prefetch = ("categories", "keywords__keyword")
    blog_posts = blog_posts.select_related("user").prefetch_related(*prefetch)
    blog_posts = paginate(blog_posts, request.GET.get("page", 1),
                          settings.BLOG_POST_PER_PAGE,
                          settings.MAX_PAGING_LINKS)
    context = {"blog_posts": blog_posts, "year": year, "month": month,
               "tag": tag, "category": category, "author": author}
    context.update(extra_context or {})
    
    return blog_posts    


def page(request, slug, template=u"pages/page.html", extra_context=None):
    """
    Select a template for a page and render it. The request
    object should have a ``page`` attribute that's added via
    ``mezzanine.pages.middleware.PageMiddleware``. The page is loaded
    earlier via middleware to perform various other functions.
    The urlpattern that maps to this view is a catch-all pattern, in
    which case the page attribute won't exist, so raise a 404 then.

    For template selection, a list of possible templates is built up
    based on the current page. This list is order from most granular
    match, starting with a custom template for the exact page, then
    adding templates based on the page's parent page, that could be
    used for sections of a site (eg all children of the parent).
    Finally at the broadest level, a template for the page's content
    type (it's model class) is checked for, and then if none of these
    templates match, the default pages/page.html is used.
    """

    from mezzanine.pages.middleware import PageMiddleware
    if not PageMiddleware.installed():
        raise ImproperlyConfigured("mezzanine.pages.middleware.PageMiddleware "
                                   "(or a subclass of it) is missing from " +
                                   "settings.MIDDLEWARE_CLASSES")

    if not hasattr(request, "page") or request.page.slug != slug:
        raise Http404

    # Check for a template name matching the page's slug. If the homepage
    # is configured as a page instance, the template "pages/index.html" is
    # used, since the slug "/" won't match a template name.
    template_name = str(slug) if slug != home_slug() else "index"
    templates = [u"pages/%s.html" % template_name]
    method_template = request.page.get_content_model().get_template_name()
    if method_template:
        templates.insert(0, method_template)
    if request.page.content_model is not None:
        templates.append(u"pages/%s/%s.html" % (template_name,
            request.page.content_model))
    for parent in request.page.get_ascendants(for_user=request.user):
        parent_template_name = str(parent.slug)
        # Check for a template matching the page's content model.
        if request.page.content_model is not None:
            templates.append(u"pages/%s/%s.html" % (parent_template_name,
                request.page.content_model))
    # Check for a template matching the page's content model.
    if request.page.content_model is not None:
        templates.append(u"pages/%s.html" % request.page.content_model)
    templates.append(template)
    
    #added by RobinWang
    ss=slug.split('/')
    if len(ss)==1:
        categorys=BlogCategory.objects.all()
        categoryslug=''
        for c in categorys:
            if c.slug==ss[0]:
                categoryslug=ss[0]
                break
        if categoryslug!='':
            blogs=getposts(request,category=categoryslug)
            extra_context['blog_posts']=blogs

    return render(request, templates, extra_context or {})
