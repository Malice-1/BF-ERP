from django.shortcuts import render

def connection(request):
    if request.method=="GET":
        template="core/templates/connection_get.html"
    if request.method=="POST":
        template="core/templates/connection_post.html"
    return render(request, template)
    
