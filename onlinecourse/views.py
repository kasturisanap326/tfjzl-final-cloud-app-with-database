
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.views import generic
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
import logging

from .models import Course, Enrollment, Question, Choice, Submission


logger = logging.getLogger(__name__)


def registration_request(request):
    context = {}

    if request.method == 'GET':
        return render(
            request,
            'onlinecourse/user_registration_bootstrap.html',
            context
        )

    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['psw']
        first_name = request.POST['firstname']
        last_name = request.POST['lastname']

        if User.objects.filter(username=username).exists():
            context['message'] = "User already exists."
            return render(
                request,
                'onlinecourse/user_registration_bootstrap.html',
                context
            )

        user = User.objects.create_user(
            username=username,
            first_name=first_name,
            last_name=last_name,
            password=password
        )

        login(request, user)
        return redirect('onlinecourse:index')

    return redirect('onlinecourse:index')


def login_request(request):
    context = {}

    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['psw']

        user = authenticate(username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect('onlinecourse:index')

        context['message'] = "Invalid username or password."

    return render(
        request,
        'onlinecourse/user_login_bootstrap.html',
        context
    )


def logout_request(request):
    logout(request)
    return redirect('onlinecourse:index')


def check_if_enrolled(user, course):
    if user.is_authenticated:
        return Enrollment.objects.filter(
            user=user,
            course=course
        ).exists()

    return False


class CourseListView(generic.ListView):
    template_name = 'onlinecourse/course_list_bootstrap.html'
    context_object_name = 'course_list'

    def get_queryset(self):
        user = self.request.user
        courses = Course.objects.order_by('-total_enrollment')[:10]

        for course in courses:
            if user.is_authenticated:
                course.is_enrolled = check_if_enrolled(user, course)

        return courses


class CourseDetailView(generic.DetailView):
    model = Course
    template_name = 'onlinecourse/course_detail_bootstrap.html'


def enroll(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    user = request.user

    if user.is_authenticated and not check_if_enrolled(user, course):
        Enrollment.objects.create(
            user=user,
            course=course,
            mode='honor'
        )

        course.total_enrollment += 1
        course.save()

    return HttpResponseRedirect(
        reverse(
            'onlinecourse:course_details',
            args=(course.id,)
        )
    )


def extract_answers(request):
    submitted_answers = []

    for key in request.POST:
        if key.startswith('choice'):
            try:
                choice_id = int(request.POST[key])
                submitted_answers.append(choice_id)
            except (TypeError, ValueError):
                continue

    return submitted_answers


def is_get_score(question, selected_ids):
    correct_ids = set(
        question.choice_set.filter(
            is_correct=True
        ).values_list('id', flat=True)
    )

    selected_question_ids = set(
        question.choice_set.filter(
            id__in=selected_ids
        ).values_list('id', flat=True)
    )

    if correct_ids and selected_question_ids == correct_ids:
        return question.grade

    return 0


@login_required
def submit(request, course_id):
    if request.method != 'POST':
        return redirect(
            'onlinecourse:course_details',
            pk=course_id
        )

    course = get_object_or_404(Course, pk=course_id)

    enrollment = get_object_or_404(
        Enrollment,
        user=request.user,
        course=course
    )

    submission = Submission.objects.create(
        enrollment=enrollment
    )

    for choice_id in extract_answers(request):
        choice = get_object_or_404(
            Choice,
            pk=choice_id,
            question__course=course
        )
        submission.choices.add(choice)

    return redirect(
        'onlinecourse:show_exam_result',
        course_id=course.id,
        submission_id=submission.id
    )


@login_required
def show_exam_result(request, course_id, submission_id):
    course = get_object_or_404(Course, pk=course_id)

    submission = get_object_or_404(
        Submission,
        pk=submission_id,
        enrollment__user=request.user,
        enrollment__course=course
    )

    questions = Question.objects.filter(
        course=course
    ).prefetch_related('choice_set')

    selected_ids = list(
        submission.choices.values_list('id', flat=True)
    )

    results = []
    grade = 0
    possible = 0

    for question in questions:
        choices = question.choice_set.all()

        selected_choices = choices.filter(
            id__in=selected_ids
        )

        correct_choices = choices.filter(
            is_correct=True
        )

        is_correct = (
            correct_choices.exists()
            and set(
                selected_choices.values_list('id', flat=True)
            )
            == set(
                correct_choices.values_list('id', flat=True)
            )
        )

        question_score = is_get_score(question, selected_ids)

        grade += question_score
        possible += question.grade

        results.append({
            'question': question,
            'choices': choices,
            'selected_choices': selected_choices,
            'is_correct': is_correct,
            'question_score': question_score,
        })

    context = {
        'course': course,
        'submission': submission,
        'results': results,
        'selected_ids': selected_ids,
        'grade': grade,
        'possible': possible,
        'score': grade,
        'total': possible,
        'passed': possible > 0 and grade >= possible * 0.5,
    }

    return render(
        request,
        'onlinecourse/exam_result_bootstrap.html',
        context
    )
