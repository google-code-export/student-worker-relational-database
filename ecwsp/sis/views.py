#   Copyright 2011 David M Burke
#   Author David M Burke <david@burkesoftware.com>
#   
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation; either version 2 of the License, or
#   (at your option) any later version.
#     
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#      
#   You should have received a copy of the GNU General Public License
#   along with this program; if not, write to the Free Software
#   Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#   MA 02110-1301, USA.

from django.shortcuts import render_to_response, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test, permission_required
from django.contrib.auth import logout
from django.conf import settings
from django.core.urlresolvers import reverse
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.template import RequestContext
from django.http import HttpResponse, HttpResponseRedirect
from django.utils.safestring import mark_safe
from datetime import date

from ecwsp.sis.models import Student, UserPreference, GradeLevel, SchoolYear
from ecwsp.sis.forms import UserPreferenceForm, UploadFileForm, StudentLookupForm, StudentReportWriterForm, UploadNaviance
from ecwsp.sis.forms import StudentGradeReportWriterForm, MarkingPeriodForm
from ecwsp.administration.models import Template
from ecwsp.sis.report import pod_report_grade, pod_report_paper_attendance, pod_report_all
from ecwsp.sis import grade_reports
from ecwsp.schedule.calendar import Calendar
from ecwsp.schedule.models import MarkingPeriod, Course

from tempfile import mkstemp
import sys
import httpagentparser

@login_required
def user_preferences(request):
    """ Displays user preferences
    """
    profile = UserPreference.objects.get_or_create(user=request.user)[0]
    if request.POST:
        form = UserPreferenceForm(request.POST, instance=profile)
        if form.is_valid():
            form.cleaned_data['user'] = request.user
            form.save()
            messages.info(request, 'Successfully updated preferences')
            if 'refer' in request.GET and request.GET['refer']:
                return HttpResponseRedirect(request.GET['refer'])
            return HttpResponseRedirect(reverse('admin:index'))
    else:
        form = UserPreferenceForm(instance=profile)
    return render_to_response('sis/user_preferences.html', {
        'form': form,
    }, RequestContext(request, {}),)


@login_required
def index(request):
    """if student, redirect them to timesheet.  if faculty allow this page
    """
    if 'next' in request.GET and request.GET['next'] != "/":
        return HttpResponseRedirect(request.GET['next'])
    if request.user.is_staff:
        try:
            # Warn users of IE and Firefox < 4.0 they are not supported
            ua = request.META['HTTP_USER_AGENT']
            browser_name = httpagentparser.detect(ua)['browser']['name']
            browser_version = httpagentparser.detect(ua)['browser']['version']
            if browser_name == "Microsoft Internet Explorer":
                messages.warning(request,
                    mark_safe('Warning Internet Explorer is not supported on the admin site. If you ' \
                              'have any trouble, try using a standards compliant browser such as Firefox, Chrome, Opera, or Safari.'))
            elif browser_name == "Firefox" and int(browser_version.split('.')[0]) < 6:
                messages.warning(request, 'Warning, your version of Firefox is out of date. Please upgrade.')
        except:
            pass
        return HttpResponseRedirect('/admin')
    elif request.user.groups.filter(Q(name='students')).count() > 0:
        return student_redirect(request)
    elif request.user.groups.filter(name='family').count() > 0:
        return family_redirect(request)
    elif request.user.groups.filter(Q(name='company')).count() > 0:
        from ecwsp.work_study.views import supervisor_dash
        return supervisor_dash(request)
    else:
        return render_to_response('base.html', {'msg': "Not authorized", 'request': request,}, RequestContext(request, {}))

def student_redirect(request):
    """ Redirects student to proper page based on what's installed and if it's possible to display the timesheet
    """
    if 'ecwsp.work_study' in settings.INSTALLED_APPS:
        from ecwsp.work_study.views import student_timesheet
        from ecwsp.work_study.models import StudentWorker
        try:
            student = StudentWorker.objects.get(username=request.user.username)
        except ObjectDoesNotExist:
            student = None
        if student and hasattr(student, 'placement') and student.placement:
            return student_timesheet(request)
    return render_to_response('base.html', {'msg': "Welcome!", 'student': 'student', 'request': request,}, RequestContext(request, {}))

def family_redirect(request):
    if 'ecwsp.benchmark_grade' in settings.INSTALLED_APPS:
        from ecwsp.benchmark_grade.views import family_grade
        return family_grade(request)
    return render_to_response('base.html', {'msg': "Welcome!", 'request': request,}, RequestContext(request, {}))

@user_passes_test(lambda u: u.groups.filter(name='registrar').count() > 0 or u.is_superuser, login_url='/')
def import_everything(request):
    """ View for handeling admin import functionality
    """
    if request.POST:
        form = UploadFileForm(request.POST, request.FILES)
        if form.is_valid():
            from ecwsp.sis.importer import Importer
            importer = Importer(request.FILES['file'], request.user)
            msg = ""
            msg_to_add, filename = importer.magic_import_everything()
            msg += msg_to_add
            form = UploadFileForm()
            return render_to_response('upload.html', {'form': form, 'msg': msg, 'error_filename':filename, 'request': request,})
        else:
            return render_to_response('upload.html', {'form': form, 'request': request,})
    form = UploadFileForm()
    return render_to_response('upload.html', {'form': form, 'request': request,}, RequestContext(request, {}))
    

@user_passes_test(lambda u: u.has_perm("sis.view_student"), login_url='/')    
def photo_flash_card(request, year=None):
    """ Simple flash card game
    """
    students = Student.objects.filter(inactive=False)
    grade_levels = GradeLevel.objects.all()
    try:
        if request.POST:
            form = StudentLookupForm(request.POST, request.FILES)
            if form.is_valid():
                student_id = form.cleaned_data['student']
            else:
                student_id = students.order_by('?')[0].pk
        else:
            form = StudentLookupForm()
            if year:
                student_id = students.filter(year=GradeLevel.objects.get(id=year)).order_by('?')[0].pk
            else:
                student_id = students.order_by('?')[0].pk
        student = Student.objects.filter(inactive=False).get(pk=student_id)
    except:
        messages.error(request, 'Student not found')
        return HttpResponseRedirect(reverse('admin:index'))
    return render_to_response('sis/flashcard.html',
                              {'form': form,
                               'student_name': student,
                               'grade_levels':grade_levels,
                               'student_img': student.pic.url_530x400,
                               'request': request}, RequestContext(request, {}))

@user_passes_test(lambda u: u.has_perm("sis.view_student"), login_url='/')  
def transcript_nonofficial(request, student_id):
    """ Build a transcripte based on template called "Transcript Nonoffical"
    """
    student = Student.objects.filter(id=student_id)
    template = Template.objects.get_or_create(name="Transcript Nonoffical")[0]
    if template.file:
        template = template.file.path
        file_format = 'pdf'
        options = {
            'date': date.today(),
            'student': student,
        }
        return pod_report_grade(template, transcript=True, options=options, students=student, format=file_format)
        
    messages.info(request, 'Please upload a templated called "Transcript Nonoffical"')
    return HttpResponseRedirect(reverse('admin:index'))


@permission_required('sis.reports') 
def school_report_builder_view(request):
    """ sis report builder view
    """
    from ecwsp.sis.pdf_reports import student_thumbnail
    if request.method == 'POST':
        if 'thumbs_fresh' in request.POST:
            return student_thumbnail(request, GradeLevel.objects.get(id=9))
        elif 'thumbs_soph' in request.POST:
            return student_thumbnail(request, GradeLevel.objects.get(id=10))
        elif 'thumbs_jun' in request.POST:
            return student_thumbnail(request, GradeLevel.objects.get(id=11))
        elif 'thumbs_sen' in request.POST:
            return student_thumbnail(request, GradeLevel.objects.get(id=12))
        elif 'p_attendance' in request.POST:
            format = UserPreference.objects.get_or_create(user=request.user)[0].get_format(type="document")
            if request.POST['p_attendance'] == "Monday":
                day = "1"
            if request.POST['p_attendance'] == "Tuesday":
                day = "2"
            if request.POST['p_attendance'] == "Wednesday":
                day = "3"
            if request.POST['p_attendance'] == "Thursday":
                day = "4"
            if request.POST['p_attendance'] == "Friday":
                day = "5"
            return pod_report_paper_attendance(day, format=format)
        elif 'pod_report' in request.POST:
            form = StudentReportWriterForm(request.POST, request.FILES)
            if form.is_valid():
                data = form.cleaned_data
                if data['template']:
                    # use selected template
                    template = data['template']
                    template = template.get_template_path(request)
                    if not template:
                        return render_to_response('sis/reportBuilder.html', {'request':request, 'form':form}, RequestContext(request, {}))
                else:
                    # or use uploaded template, saving it to temp file
                    template = request.FILES['upload_template']
                    tmpfile = mkstemp()[1]
                    f = open(tmpfile, 'wb')
                    f.write(template.read())
                    f.close()
                    template = tmpfile
                format = UserPreference.objects.get_or_create(user=request.user)[0].get_format(type="document")
                return pod_report_all(template, options=data, students=form.get_students(data), format=format)
            else:
                return render_to_response('sis/reportBuilder.html', {'request':request, 'form':form})
    else:
        form = StudentReportWriterForm()
        form.fields['template'].queryset = Template.objects.filter(general_student=True)
        return render_to_response('sis/reportBuilder.html', {'request':request, 'form':form}, RequestContext(request, {}))


def logout_view(request):
    """ Logout, by sending a message to the base.html template
    """
    logout(request)
    msg = mark_safe('You have been logged out. Click <a href="/">here</a> to log back in.')
    return render_to_response('base.html', {'msg': msg,}, RequestContext(request, {}))


@user_passes_test(lambda u: u.groups.filter(name='faculty').count() > 0 or u.is_superuser, login_url='/')
def student_page_redirect(request, student_id):
    """ Redirects user to highest level of permission they have for a student
    """
    try:
        from ecwsp.work_study.models import StudentWorker
    except ImportError:
        pass
    if request.user.has_perm(StudentWorker):
        return HttpResponseRedirect(reverse('admin:work_study_studentworker_change', args=(student_id,)))
    return HttpResponseRedirect(reverse('admin:sis_student_change', args=(student_id,)))

@permission_required('sis.change_student')
def import_naviance(request):
    """ Import only naviance data
    """
    msg = 'Import a test directly from Naviance such as SAT and ACT. You must have unique id (SWORD) and hs_student_id (Naviance)' \
          ' be the same. You must have already set up the <a href="/admin/schedule/standardtest/"> tests </a> <br/>' \
          'In Naviance, click setup, then Import/Export then export the test you want. At this time only SAT and ACT is supported.'
    if request.method == 'POST':
        form = UploadNaviance(request.POST, request.FILES)
        if form.is_valid():
            test = form.cleaned_data['test']
            from ecwsp.sis.importer import Importer
            importer = Importer(file=form.cleaned_data['import_file'], user=request.user)
            msg, filename = importer.import_just_standard_test(test)
            msg += '<br/><a href="/media/import_error.xls">Download Errors</a>'
    else:
        form = UploadNaviance()
    msg = mark_safe(msg)
    return render_to_response('sis/generic_form.html', {'form':form, 'msg':msg}, RequestContext(request, {}), )

@user_passes_test(lambda u: u.groups.filter(name="registrar").count() or u.has_perm('sis.reports') or u.is_superuser, login_url='/')   
def grade_report(request):
    """ Grade related report builder
    """
    form = StudentGradeReportWriterForm()
    mp_form = MarkingPeriodForm()
    
    if request.method == 'POST':
        if 'student_grade' in request.POST:
            form = StudentGradeReportWriterForm(request.POST, request.FILES)
            if form.is_valid():
                return grade_reports.student_grade(request, form)
        elif 'aggregate_grade_report' in request.POST:
            return grade_reports.aggregate_grade_report(request)
        elif 'fail_report' in request.POST:
            return grade_reports.fail_report(request)
        elif 'date_based_gpa_report' in request.POST:
            return grade_reports.date_based_gpa_report(request)
                
    form.fields['template'].queryset = Template.objects.filter(Q(report_card=True) | Q(transcript=True))
    return render_to_response('sis/grade_report.html', {'form':form, 'mp_form':mp_form}, RequestContext(request, {}),)

@login_required
def ajax_include_deleted(request):
    """ ajax call to enable or disable user preference to search for inactive students
    """
    checked = request.GET.get('checked')
    profile = UserPreference.objects.get_or_create(user=request.user)[0]
    if checked == "true":
        profile.include_deleted_students = True
    else:
        profile.include_deleted_students = False
    profile.save()
    return HttpResponse('SUCCESS')

@user_passes_test(lambda u: u.has_perm("sis.view_student"), login_url='/')   
def view_student(request, id=None):
    """ Lookup all student information
    """
    if request.method == "GET":
        if id and 'next' in request.GET or 'previous' in request.GET:
            current_student = get_object_or_404(Student, pk=id)
            found = False
            preference = UserPreference.objects.get_or_create(user=request.user)[0]
            if 'next' in request.GET:
                if preference.include_deleted_students:
                    students = Student.objects.order_by('lname','fname')
                else:
                    students = Student.objects.filter(inactive=False).order_by('lname','fname')
            elif 'previous' in request.GET:
                if preference.include_deleted_students:
                    students = Student.objects.order_by('-lname','-fname')
                else:
                    students = Student.objects.filter(inactive=False).order_by('-lname','-fname')
            for student in students:
                if found:
                    return HttpResponseRedirect('/sis/view_student/' + str(student.id))
                if student == current_student:
                    found = True
                    
    if request.method == 'POST':
        form = StudentLookupForm(request.POST)
        if form.is_valid():
            return HttpResponseRedirect('/sis/view_student/' + str(form.cleaned_data['student'].id))
            
    profile = UserPreference.objects.get_or_create(user=request.user)[0]
    
    student = get_object_or_404(Student, pk=id)
    
    today = date.today()
    emergency_contacts = student.emergency_contacts.all()
    siblings = student.siblings.all()
    numbers = student.studentnumber_set.all()
    
    # Schedule
    cal = Calendar()
    try:
        location = cal.find_student(student)
    except:
        location = None
        print >> sys.stderr, str(sys.exc_info()[0])
    # Guess the mp desired (current or next coming)
    schedule_days = None
    periods = None
    current_mp = MarkingPeriod.objects.filter(end_date__gte=today).order_by('-start_date')
    if current_mp:
        current_mp = current_mp[0]
        schedule_days, periods = cal.build_schedule(student, current_mp, include_asp=True)
    else:
        schedule_days = None
        periods = None
    
    # Discipline
    if 'ecwsp.discipline' in settings.INSTALLED_APPS:
        disciplines = student.studentdiscipline_set.all()
    else:
        disciplines = None
    attendances = student.student_attn.all()
    
    #### CWSP related
    try:
        clientvisits = student.studentworker.clientvisit_set.all()
    except:
        clientvisits = None
    try:
        company_histories = student.studentworker.companyhistory_set.all()
    except:
        company_histories = None
    try:
        timesheets = student.studentworker.timesheet_set.exclude(Q(performance__isnull=True) | Q(performance__exact=''))
    except:
        timesheets = None
    try:
        if request.user.has_perm("sis.view_mentor_student"):
            student_interactions = student.studentworker.studentinteraction_set.all()
        else:
            student_interactions = None
    except:
        student_interactions = None
    try:
        supervisors = student.studentworker.placement.contacts.all()
    except:
        supervisors = None
    ########################################################################
    
    #Grades
    years = SchoolYear.objects.filter(markingperiod__course__courseenrollment__user=student).distinct()
    from ecwsp.grades.models import Grade
    for year in years:
        year.mps = MarkingPeriod.objects.filter(course__courseenrollment__user=student, school_year=year).distinct().order_by("start_date")
        year.courses = Course.objects.filter(courseenrollment__user=student, graded=True, marking_period__school_year=year).distinct()
        for course in year.courses:
            # Too much logic for the template here, so just generate html.
            course.grade_html = ""
            for marking_period in year.mps:
                try:
                    course.grade_html += '<td> %s </td>' % (
                        Grade.objects.get(student=student, course=course, marking_period=marking_period).get_grade(),)
                except:
                    course.grade_html += '<td> </td>'
            course.grade_html += '<td> %s </td>' % (unicode(course.get_final_grade(student)),)
            
    #Standard Tests
    from ecwsp.administration.models import Configuration
    from ecwsp.schedule.models import StandardCategory, StandardCategoryGrade, StandardTest, StandardTestResult
    std_test_config = Configuration.get_or_default("Standard Tests in View Student",default="False")
    if std_test_config.value.lower() == "false" or std_test_config.value.lower == "f":
        std = None
    else:
        std = StandardTestResult.objects.filter(student=student)
        
    
    return render_to_response('sis/view_student.html', {
        'date':today,
        'student':student,
        'emergency_contacts': emergency_contacts,
        'siblings': siblings,
        'numbers':numbers,
        'location':location,
        'disciplines':disciplines,
        'attendances':attendances,
        'student_interactions': student_interactions,
        'clientvisits':clientvisits,
        'supervisors':supervisors,
        'company_histories':company_histories,
        'timesheets':timesheets,
        'years': years,
        'current_mp': current_mp,
        'schedule_days':schedule_days,
        'periods': periods,
        'include_inactive': profile.include_deleted_students,
        'tests': std
    }, RequestContext(request, {}),)

def increment_year_or_graduate(request):
    selected = request.GET['ids'].split(',')
    students = Student.objects.filter(id__in=selected)
    subtitle = "Are you sure you want to make the following changes?"
    
    if request.POST:
        for student in students:
            if student.year:
                if student.year.id == 12:
                    student.graduate_and_create_alumni()
                else:
                    try:
                        new_year = GradeLevel.objects.get(id=student.year.id + 1)
                        student.year = new_year
                        student.save()
                    except GradeLevel.DoesNotExist:
                        pass
        messages.success(request, 'Successfully incremented student years!')
        return HttpResponseRedirect(reverse('admin:sis_student_changelist'))
        
    item_list = []
    for student in students:
        row = None
        if student.year:
            if student.year.id == 12:
                row = '%s - Graduate and mark inactive %s.' % (unicode(student), student.year)
                if 'ecwsp.alumni' in settings.INSTALLED_APPS:
                    row += ' Also make an alumni record.'
            else:
                try:
                    new_year = GradeLevel.objects.get(id=student.year.id + 1)
                    row = '%s - Make a %s.' % (unicode(student), new_year)
                except SchoolYear.DoesNotExist:
                    pass
        if row:
            item_list += [row]
    
    return render_to_response('sis/list_with_confirm.html', {'subtitle': subtitle, 'item_list':item_list}, RequestContext(request, {}),)
