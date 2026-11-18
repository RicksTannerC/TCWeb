"""The curator's console: the message inbox and the content pages."""

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from shop.console import ContactMessage, Page


# ------------------------------------------------------------------ messages

def _inbox_context(request):
    show = request.GET.get("show", "open")
    qs = ContactMessage.objects.select_related("order")
    if show == "open":
        qs = qs.filter(handled=False)
    return {"messages_list": qs, "show": show}


@staff_member_required
def inbox(request):
    """Old standalone URL: messages now live on the merged Content page."""
    qs = request.META.get("QUERY_STRING", "")
    return redirect(reverse("shop:manage_content") + (f"?{qs}" if qs else "") + "#messages")


@staff_member_required
@require_POST
def message_toggle(request, pk):
    m = get_object_or_404(ContactMessage, pk=pk)
    m.handled = not m.handled
    m.save(update_fields=["handled"])
    return redirect(request.POST.get("next") or "shop:manage_inbox")




# ------------------------------------------------------------------ pages

@staff_member_required
def pages(request):
    """Old standalone URL: pages now live on the merged Content page."""
    return redirect(reverse("shop:manage_content") + "#pages")


@staff_member_required
def content(request):
    """Messages (inbox) + Pages, one page: both lower-frequency content/comms tasks."""
    return render(request, "shop/manage/content.html", {
        **_inbox_context(request),
        "pages": Page.objects.all(),
    })


@staff_member_required
def page_edit(request, pk=None):
    page = get_object_or_404(Page, pk=pk) if pk else Page()
    if request.method == "POST":
        page.title = request.POST.get("title", "").strip() or "Untitled"
        if request.POST.get("slug", "").strip():
            page.slug = slugify(request.POST["slug"])
        page.body = request.POST.get("body", "")
        page.meta_description = request.POST.get("meta_description", "").strip()
        page.status = request.POST.get("status", Page.Status.DRAFT)
        page.show_in_footer = bool(request.POST.get("show_in_footer"))
        page.footer_order = int(request.POST.get("footer_order") or 0)
        page.save()
        messages.success(request, f"“{page.title}” saved.")
        return redirect("shop:manage_page_edit", pk=page.pk)
    return render(request, "shop/manage/page_edit.html", {"page": page, "statuses": Page.Status.choices})
