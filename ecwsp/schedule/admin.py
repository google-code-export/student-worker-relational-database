from django.contrib import admin
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.http import HttpResponseRedirect

from ajax_select import make_ajax_form
from ajax_select.fields import autoselect_fields_check_can_add

from ecwsp.sis.models import *
from ecwsp.schedule.models import *

def copy(modeladmin, request, queryset):
    for object in queryset:
        object.copy_instance(request)

class CourseMeetInline(admin.TabularInline):
    model = CourseMeet
    extra = 1

class CourseAdmin(admin.ModelAdmin):
    def render_change_form(self, request, context, *args, **kwargs):
        try:
            txt = "<h5>Students enrolled:</h5>"
            for student in context['original'].get_enrolled_students():
                txt += unicode(student) + '<br/>'
            txt = txt[:-5]
            context['adminform'].form.fields['teacher'].help_text += txt
        except:
            pass
        return super(CourseAdmin, self).render_change_form(request, context, args, kwargs)
    
    list_display = ['__unicode__', 'teacher', 'grades_link']
    search_fields = ['fullname', 'shortname', 'description', 'teacher__username']
    list_filter = ['homeroom', 'graded', 'teacher', 'marking_period', 'active']
    inlines = [CourseMeetInline]
    actions = [copy]
    
    def save_model(self, request, obj, form, change):
        """Override save_model because django doesn't have a better way to access m2m fields"""
        obj.save()
        form.save_m2m()
        obj.save()
        
    
admin.site.register(Course, CourseAdmin)
admin.site.register(Department)

class DaysOffInline(admin.TabularInline):
    model = DaysOff
    extra = 1
    

admin.site.register(Day)

    
class CourseEnrollmentAdmin(admin.ModelAdmin):
    search_fields = ['course__fullname', 'user__username', 'user__fname', 'role']
    list_display = ['course', 'user', 'role', 'attendance_note']
admin.site.register(CourseEnrollment, CourseEnrollmentAdmin)

class MarkingPeriodAdmin(admin.ModelAdmin):
    inlines = [DaysOffInline]
admin.site.register(MarkingPeriod, MarkingPeriodAdmin)

admin.site.register(Period)

admin.site.register(Faculty)

admin.site.register(Location)

admin.site.register(OmitCourseGPA)

admin.site.register(OmitYearGPA)


class StandardCategoryInline(admin.TabularInline):
    model = StandardCategory
    extra = 1
class StandardTestAdmin(admin.ModelAdmin):
    inlines = (StandardCategoryInline,)
admin.site.register(StandardTest, StandardTestAdmin)

class StandardCategoryGradeInline(admin.TabularInline):
    model = StandardCategoryGrade
    extra = 1
class StandardTestResultAdmin(admin.ModelAdmin):
    inlines = (StandardCategoryGradeInline,)
    list_display = ['student', 'test', 'date']
    list_filter = ['test']
    search_fields = ['student__fname', 'student__lname', 'test__name']
admin.site.register(StandardTestResult, StandardTestResultAdmin)

admin.site.register(Award)
