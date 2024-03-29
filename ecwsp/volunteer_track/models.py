#   Copyright 2011 David M Burke
#   Author Callista Goss <calli@burkesoftware.com>
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


from django.db import models
from django.db.models import Sum
from django.contrib.localflavor.us.models import *
from django.contrib import messages

from datetime import datetime
import random
import sys
import logging

from ecwsp.administration.models import Configuration

class Hours(models.Model):
    volunteer_site = models.ForeignKey('VolunteerSite')
    date = models.DateField(blank = False, null = False)
    hours = models.FloatField()
    time_stamp = models.DateTimeField(auto_now_add=True)
    class Meta:
        verbose_name = "Hours"
        verbose_name_plural = "Hours"
        unique_together = ("volunteer_site","date")
    def __unicode__(self):
        return unicode(self.hours)

class Site(models.Model):
    site_name = models.CharField(max_length=255, unique=True)
    site_address = models.CharField(max_length=511)
    site_city = models.CharField(max_length=768)
    site_state = models.CharField(max_length=30)
    site_zip = models.CharField(max_length=30)
    def __unicode__(self):
        return unicode(self.site_name)

class SiteSupervisor(models.Model):
    name = models.CharField(max_length=200)
    site = models.ForeignKey('Site',blank=True,null=True)
    phone = PhoneNumberField(max_length=40, blank=True)
    email = models.EmailField(max_length=200, blank=True)
    def __unicode__(self):
        return unicode(self.name)

class VolunteerSite(models.Model):
    inactive = models.BooleanField()
    volunteer = models.ForeignKey('Volunteer')
    site = models.ForeignKey(Site)
    supervisor = models.ForeignKey(SiteSupervisor,blank=True,null=True)
    site_approval = models.CharField(max_length=16, choices=(('Accepted','Accepted'),('Rejected', 'Rejected'),('Submitted', 'Submitted')), blank=True)
    contract = models.BooleanField()
    job_description = models.TextField(blank=True)
    hours_confirmed = models.BooleanField()
    comment = models.TextField(blank=True)
    secret_key = models.CharField(max_length=20, blank=True, editable=False)
    
    def __unicode__(self):
        return '%s at %s' % (self.volunteer,self.site)
    
    def genKey(self):
        key = ''
        alphabet = 'abcdefghijklmnopqrstuvwxyz1234567890_-'
        for x in random.sample(alphabet,random.randint(19,20)):
            key += x
        self.secret_key = key
    
    def save(self, saved_by_volunteer=False, *args, **kwargs):
        if not self.secret_key or self.secret_key == "":
            self.genKey()
        
        if saved_by_volunteer:
            if not self.volunteer.email_queue:
                self.volunteer.email_queue = ""
            self.volunteer.email_queue += "Added Site %s. " % (unicode(self.site))
            self.volunteer.save()
        if self.id:
            old_volunteer = VolunteerSite.objects.get(id=self.id)
            if old_volunteer.site_approval == "Submitted" and self.site_approval == "Accepted":
                try:
                    from django.core.mail import send_mail
                    from_email = Configuration.get_or_default("From Email Address",default="donotreply@change.me").value
                    msg = "Hello %s,\nYour site %s has been approved!" % (self.volunteer, self.site)
                    emailEnd = Configuration.get_or_default("email", default="@change.me").value
                    subject = "Site approval"
                    send_to = str(self.volunteer.student.username) + emailEnd
                    send_mail(subject, msg, from_email, [send_to])
                except:
                    exc_type, exc_obj, exc_tb = sys.exc_info()
                    fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
                    logging.warning(
                        'Unable to send email to volunteer about site approval! %s' % (self,),
                        exc_info=True,
                        extra={'request': request,'exception':exc_type,'traceback':'%s %s' % (fname,exc_tb.tb_lineno)}
                        )
        super(VolunteerSite, self).save(*args, **kwargs)
    
    def send_email_approval(self):
        """
        Send email to supervisor for approval
        """
        if not self.site_supervisor or not self.site_supervisor.email:
            return None
        try:
            sendTo = self.site_supervisor.email
            subject = "Volunteer hours approval for " + unicode(self.student)
            msg = "Hello " + unicode(self.site_supervisor.name) + ",\nPlease click on the link below to approve the time sheet\n" + \
                settings.BASE_URL + "/volunteer_tracker/approve?key=" + str(self.secret_key)
            from_addr = Configuration.get_or_default("From Email Address", "donotreply@example.org").value
            send_mail(subject, msg, from_addr, [sendTo])
        except:
            logging.warning("Unable to send email to volunteer's supervisor! %s" % (self,), exc_info=True)
    
    def hours_at_site(self):
        return self.hours_set.all().aggregate(Sum('hours'))['hours__sum']

def get_hours_default():
    return Configuration.get_or_default('Volunteer Track Required Hours', default=20).value
class Volunteer(models.Model):
    student = models.OneToOneField('sis.Student')
    sites = models.ManyToManyField(Site,blank=True,null=True,through='VolunteerSite')
    attended_reflection = models.BooleanField(verbose_name = "Attended")
    hours_required = models.IntegerField(default=get_hours_default, blank=True, null=True)
    notes = models.TextField(blank=True)
    last_updated = models.DateTimeField(default = datetime.now)
    email_queue = models.CharField(default="", max_length=1000, blank=True, editable=False, help_text="Used to store nightly notification emails")
    def __unicode__(self):
        return unicode(self.student)
            
    def hours_completed(self):
        return self.volunteersite_set.all().aggregate(Sum('hours__hours'))['hours__hours__sum']
