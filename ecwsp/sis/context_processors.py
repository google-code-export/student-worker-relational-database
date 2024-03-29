# sis/context_processors.py
from django.conf import settings
import datetime
from ecwsp.sis.models import MessageToStudent
from ecwsp.administration.models import Configuration

def global_stuff(request):
    try:
        header_image = Configuration.objects.get_or_create(name="Header Logo")[0].file.url
    except:
        header_image = None
    school_name = Configuration.get_or_default('School Name', default="Unnamed School")
    school_color = Configuration.get_or_default('School Color', default="").value
    
    # Only show messages if user just logged in
    user_messages = None
    if not request.session.get('has_seen_message', False):
        today = datetime.date.today()
        if request.user.groups.filter(name='students'):
            user_messages = MessageToStudent.objects.filter(start_date__lte=today, end_date__gte=today)
        if request.user.groups.filter(name='company') and 'ecwsp.work_study' in settings.INSTALLED_APPS:
            from ecwsp.work_study.models import MessageToSupervisor
            user_messages = MessageToSupervisor.objects.filter(start_date__lte=today, end_date__gte=today)
        request.session['has_seen_message'] = True
            
    return {
        "header_image": header_image,
        "school_name": school_name,
        "settings": settings,
        "school_color": school_color,
        'user_messages':user_messages,
    }