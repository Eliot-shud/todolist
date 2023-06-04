from django.db import transaction
from rest_framework import serializers, request
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework.request import Request

from core.models import User
from core.serializers import UserSerializer
from goals.models import GoalCategory, Goal, GoalComments, Board, BoardParticipant


class GoalCategorySerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())

    def validate_board(self, board: Board) -> Board:
        if board.is_deleted:
            raise ValidationError("board is deleted")

        if not BoardParticipant.objects.filter(
            board_id=board.id,
            role__in=[BoardParticipant.Role.owner, BoardParticipant.Role.writer],
            user_id=self.context["request"].user
        ).exists():
            raise PermissionDenied

        return board

    class Meta:
        model = GoalCategory
        fields = "__all__"
        read_only_fields = ("id", "created", "updated", "user", "is_deleted")


class GoalCategoryWithUserSerializer(GoalCategorySerializer):
    user = UserSerializer(read_only=True)


class GoalSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = Goal
        fields = "__all__"
        read_only_fields = ("id", "created", "updated", "user")

    def validate_category(self, value: GoalCategory) -> GoalCategory:
        if value.is_deleted:
            raise ValidationError("Category not found")

        if not BoardParticipant.objects.filter(
                board_id=value.board,
                role__in=[BoardParticipant.Role.owner, BoardParticipant.Role.writer],
                user_id=self.context["request"].user
        ).exists():
            raise PermissionDenied
        return value

    # Написать проверку чтобы дата дедлайна не была меньше текущей


class GoalWithUserSerializer(GoalSerializer):
    user = UserSerializer(read_only=True)


class GoalCommentsSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = GoalComments
        fields = "__all__"
        read_only_fields = ("id", "created", "updated", "user")

    def validate_goal(self, value: Goal) -> Goal:
        if value.status == Goal.Status.archived:
            raise ValidationError("Goal not found")
        if not BoardParticipant.objects.filter(
                board_id=value.category.board_id,
                role__in=[BoardParticipant.Role.owner, BoardParticipant.Role.writer],
                user_id=self.context["request"].user
        ).exists():
            raise PermissionDenied
        return value


class GoalCommentWithUserSerializer(GoalCommentsSerializer):
    user = UserSerializer(read_only=True)
    goal = serializers.PrimaryKeyRelatedField(read_only=True)


class BoardSerializer(serializers.ModelSerializer):

    class Meta:
        model = Board
        fields = "__all__"
        read_only_fields = ("id", "created", "updated", "is_deleted")


class BoardParticipantSerializer(serializers.ModelSerializer):
    role = serializers.ChoiceField(required=True, choices=BoardParticipant.editable_roles)
    user = serializers.SlugRelatedField(slug_field="username", queryset=User.objects.all())

    def validate_user(self, user: User) -> User:
        if self.context["request"].user == user:
            raise ValidationError("Failed to change your role")
        return user

    class Meta:
        model = BoardParticipant
        fields = "__all__"
        read_only_fields = ("id", "created", "updated", "board")


class BoardWithParticipantSerializer(BoardSerializer):
    participants = BoardParticipantSerializer(many=True)

    def update(self, instance: Board, validated_data: dict) -> Board:
        requests: Request = self.context["request"]

        with transaction.atomic():
            BoardParticipant.objects.filter(board=instance).exclude(user=request.user).delete()
            BoardParticipant.objects.bulk_create(
                [
                    BoardParticipant(user=participant["user"], role=participant["role"], board=instance)
                    for participant in validated_data.get("participants", [])
                ],
                ignore_conflicts=True
            )

            if title := validated_data.get("title"):
                instance.title = title

            instance.save()

        return instance
