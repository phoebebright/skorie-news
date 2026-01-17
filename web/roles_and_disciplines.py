import logging

from django.conf import settings
from django.contrib.humanize.templatetags.humanize import ordinal
from django.utils.module_loading import import_string

logger = logging.getLogger('django')

class Disciplines(object):

    DISCIPLINE_ANY = "*"
    DISCIPLINE_DRESSAGE = "D"
    DISCIPLINE_WESTERN_DRESSAGE = "W"
    DISCIPLINE_WORKING_EQUITATION_DRESSAGE = "E"
    DISCIPLINE_SHOWJUMPING = "J"
    DISCIPLINE_CROSSCOUNTRY = "X"
    DISCIPLINE_DRIVING = "V"
    DISCIPLINE_SHOWING = "S"

    DEFAULT_DISCIPLINE = DISCIPLINE_DRESSAGE


    DISCIPLINE_CHOICES = (
        (DISCIPLINE_DRESSAGE, "Dressage"),
        (DISCIPLINE_WESTERN_DRESSAGE, "Western Dressage"),
        (DISCIPLINE_WORKING_EQUITATION_DRESSAGE, "Working Equitation Dressage"),
        (DISCIPLINE_SHOWJUMPING, "Show Jumping"),
        (DISCIPLINE_CROSSCOUNTRY, "Cross Country"),
        (DISCIPLINE_SHOWING, "Showing"),
        (DISCIPLINE_ANY, "Any"),
        # (DISCIPLINE_CROSSCOUNTRY, "Cross Country"),

    )

    DISCIPLINES_IN_USER = [k for k,v in DISCIPLINE_CHOICES]

    @property
    def default(self):
        return self.DISCIPLINE_DRESSAGE

    @classmethod
    def codes(cls):
        return [code for code,name in cls.DISCIPLINE_CHOICES]

    def fei_code(self):
        '''
        S Jumping
D Dressage
C Eventing
A Driving
E Endurance
R Reining
V Vaulting
PED Para-Equestrian Dressage
PEA Para-Equestrian Driving
        :return:
        '''
        return "D"

class ModelRoles(object):
    ROLE_ADMINISTRATOR = "A"  # can administor skorie - God
    ROLE_MANAGER = "M"   # can create new events

    ROLE_ISSUER = "I"  # can add testsheets
    ROLE_JUDGE = "J"
    ROLE_AUXJUDGE = "K" # auxiliarry judge - judge for just one event, eg. trainee judge or try judging competitor
    ROLE_ORGANISER = "O"  # can organise a specific event
    ROLE_RIDER = "R"
    ROLE_COMPETITOR = "R"
    ROLE_SCORER = "S"
    ROLE_SCORER_BASIC = "B"
    ROLE_STEWARD = "E"
    ROLE_SYSTEM = "Y"
    ROLE_WRITER = "W"
    ROLE_DEFAULT = "D"
    ROLE_DOGSBODY = "G"
    ROLE_LEADER = "L" # person leading clinic, eg. Instructor

    ROLE_DESCRIPTIONS = {
        ROLE_ADMINISTRATOR: "Administer the Skorie system", # - will require manual addition of is_staff and superuser on model for some options",
        ROLE_MANAGER: "Manage events - can create new events",
        ROLE_ISSUER: "Manage a list of testsheets on behalf of a test issuer",
        ROLE_JUDGE: "Can judge at event",
        ROLE_AUXJUDGE: "Can practise judge at event",
        ROLE_ORGANISER: "Can organise a specific event",
        ROLE_COMPETITOR: "Can compete at an event",
        ROLE_SCORER: "Can manage scores at an event",
        ROLE_SCORER_BASIC : "Can score at an event",
        ROLE_STEWARD: "Can steward at an event",
        ROLE_SYSTEM: "Non-user role - used to tag data created by the system",
        ROLE_WRITER: "Can write for a judge at an event",
        ROLE_DEFAULT: "Default role for new user",
        ROLE_DOGSBODY: "Can have general support role at event",
        ROLE_LEADER: "Teacher, presenter, coach at clinic - main leadership role",

    }

    # the order of this list will be used when picking the current user mode (role) if they have more than one
    EVENT_ROLES = {

        ROLE_ORGANISER: "Organiser",  # can organise an event but can't create a new one
        ROLE_JUDGE: "Judge",
        ROLE_LEADER: "Leader",
        ROLE_AUXJUDGE: "Trainee Judge",
        ROLE_SCORER_BASIC: "Scorer",
        ROLE_SCORER: "Scorer Pro",
        ROLE_STEWARD: "Steward",
        ROLE_WRITER: "Writer",
        ROLE_DOGSBODY: "Dogsbody",
        ROLE_COMPETITOR: "Competitor",
    }

    VIRTUAL_EVENT_ROLES = {
        ROLE_ORGANISER: "Organiser",
        ROLE_JUDGE: "Judge",
        ROLE_AUXJUDGE: "Trainee Judge",
    }



    NON_EVENT_ROLES = {
        ROLE_ADMINISTRATOR: "Administrator",
        ROLE_MANAGER: "Event Manager",  # can create and event and gets Organiser role for event
        ROLE_ISSUER: "Issuer",
        ROLE_JUDGE: "Judge",
        ROLE_AUXJUDGE: "Trainee Judge",
        ROLE_COMPETITOR: "Competitor",
        ROLE_DEFAULT: "Default",
    }

    SYSTEM_ROLES = {
        ROLE_SYSTEM: "System",

    }


    #ROLES = dict(EVENT_ROLES.items()  + NON_EVENT_ROLES.items())
    ROLES = EVENT_ROLES.copy()
    ROLES.update(NON_EVENT_ROLES)


    # when adding roles a primary role is requested, eg organiser or judge, so that correct lookups can be done
    # additional roles do not include primary roles with specific looksups
    PRIMARY_EVENT_ROLES = {
        ROLE_ORGANISER: "Organiser",
        ROLE_JUDGE: "Judge",
        ROLE_SCORER_BASIC: "Scorer",
        ROLE_SCORER: "Scorer Pro",

        ROLE_STEWARD: "Steward",
        ROLE_WRITER: "Writer",
        ROLE_DOGSBODY: "Dogsbody",
    }
    ADDITIONAL_EVENT_ROLES =  {
        ROLE_SCORER_BASIC: "Scorer",
        ROLE_SCORER: "Scorer Pro",
        ROLE_STEWARD: "Steward",
        ROLE_WRITER: "Writer",
        ROLE_DOGSBODY: "Dogsbody",
        ROLE_AUXJUDGE: "Trainee Judge",
    }

    EVENT_ROLES_LIST = [role for role, _ in EVENT_ROLES.items()]
    EVENT_ROLES_LIST_NO_JUDGES = [ROLE_ORGANISER,ROLE_SCORER,ROLE_SCORER_BASIC,ROLE_STEWARD,ROLE_WRITER,ROLE_DOGSBODY]

    #NameError: name 'EVENT_ROLES_LIST_NO_JUDGES' is not defined?????
    #EVENT_ROLES_NO_JUDGES_CHOICES = [(key, value) for key,value in PRIMARY_EVENT_ROLES.items() if key in EVENT_ROLES_LIST_NO_JUDGES]

    VIRTUAL_EVENT_PRIMARY_ROLES = {
        ROLE_ORGANISER: "Organiser",
        ROLE_JUDGE: "Judge",
    }
    VIRTUAL_EVENT_ADDITIONAL_ROLES = {
        ROLE_AUXJUDGE: "Trainee Judge",
    }


    ROLE_CHOICES  = [(key, value) for key,value in ROLES.items()]
    EVENT_ROLE_CHOICES = [(key, value) for key,value in EVENT_ROLES.items()]

    # roles that can be chosen
    PRIMARY_ROLES_CHOICES = [(key, value) for key,value in PRIMARY_EVENT_ROLES.items()]
    ADDITIONAL_ROLES_CHOICES = [(key, value) for key,value in ADDITIONAL_EVENT_ROLES.items()]

    VIRTUAL_PRIMARY_ROLES_CHOICES = [(key, value) for key,value in VIRTUAL_EVENT_PRIMARY_ROLES.items()]
    VIRTUAL_ADDITIONAL_ROLES_CHOICES = [(key, value) for key,value in VIRTUAL_EVENT_ADDITIONAL_ROLES.items()]


    NON_EVENT_CHOICES = [(key, value) for key,value in NON_EVENT_ROLES.items()]
    EVENT_CHOICES = EVENT_ROLE_CHOICES
    ORGANISER_ROLES = [ROLE_ORGANISER,ROLE_SCORER,ROLE_SCORER_BASIC,ROLE_STEWARD,ROLE_WRITER,ROLE_DOGSBODY]

    JUDGE_ROLES = [ROLE_JUDGE,ROLE_AUXJUDGE]
    JUDGE_ROLE_CHOICES = [(ROLE_JUDGE,EVENT_ROLES[ROLE_JUDGE]),(ROLE_AUXJUDGE, EVENT_ROLES[ROLE_AUXJUDGE])]



    @classmethod
    def is_valid_role(cls, role):

        # check role is valid
        if len(role) != 1:
            return False

        try:
            ok = cls.ROLES[role]
        except:
            return False

        return True

    @classmethod
    def validate_roles(cls, roles):
        '''return list of valid roles from list of unvalidated roles'''
        valid_roles = []
        for item in roles:
            if item > "" and not ModelRoles.is_valid_role(item):
                logger.warning(f"trying to add invalid role {item} to event team")
            else:
                valid_roles.append(item)

        return valid_roles




class CompetitionTypeParams(object):
    VIRTUAL_CHOICES = (
        ("T", "Yes"),
        ("F", "No"),
        ("*", "Any"),
    )
    PLACING_MODEL_HIGH_SCORE_HIGH_TIEBREAK_IS_BETTER = "HH"
    PLACING_MODEL_LOW_SCORE_HIGH_TIEBREAK_IS_BETTER = "LH"
    PLACING_MODEL_HIGH_SCORE_LOW_TIEBREAK_IS_BETTER = "HL"
    PLACING_MODEL_LOW_SCORE_LOW_TIEBREAK_IS_BETTER = "LL"
    PLACING_MODEL_NO_PLACINGS = "-"
    PLACING_MODEL_CHOICES = (
        (PLACING_MODEL_HIGH_SCORE_HIGH_TIEBREAK_IS_BETTER, 'score high, tiebreak high - eg. pure dressage'),
        (PLACING_MODEL_HIGH_SCORE_LOW_TIEBREAK_IS_BETTER, 'score low, tiebreak high - eg. eventing'),
        (PLACING_MODEL_HIGH_SCORE_LOW_TIEBREAK_IS_BETTER, 'score high, tiebreak low'),
        (PLACING_MODEL_LOW_SCORE_LOW_TIEBREAK_IS_BETTER, 'score low, tiebreak low eg. sj'),
        (PLACING_MODEL_NO_PLACINGS, "No Placings"),
    )
    DEFAULT_PLACING_MODEL = "HH"

    RESULTS_MODEL_DRESSAGE = "D"
    RESULTS_MODEL_JUMPING = "J"
    RESULTS_MODEL_GENERIC_SCORE = "GS"   # default should be HH placing model
    RESULTS_MODEL_GENERIC_TIEBREAK = "G"
    RESULTS_MODEL_PLACING_ONLY = "P"    # implies LL placing model
    RESULTS_MODEL_POINTS_ONLY = "PT"

    RESULTS_MODEL_CHOICES = (
        (RESULTS_MODEL_DRESSAGE, 'Dressage - Percentage + Penalties + Collectives'),
        (RESULTS_MODEL_JUMPING, 'Score is Faults, Tiebreak is Time'),
        (RESULTS_MODEL_GENERIC_SCORE, 'Generic - Score Only'),
        (RESULTS_MODEL_GENERIC_TIEBREAK, 'Generic Score + Tiebreak'),
        (RESULTS_MODEL_PLACING_ONLY, 'Placing only - no scores shown'),
        (RESULTS_MODEL_POINTS_ONLY, 'Points only'),
    )
    DEFAULT_RESULTS_MODEL = RESULTS_MODEL_GENERIC_SCORE

    JUDGING_MODEL_PREDEFINED = "D"
    JUDGING_MODEL_SELF_ASSESSED = "A"  # used for online training - no scoresheet
    JUDGING_MODEL_MANY_OF_MANY = "M"  # used for online judges training - anyone can judge
    # JUDGING_MODEL_2ROUND = "S"
    JUDGING_MODEL_1OFMANY = "O"
    JUDGING_MODEL_NO_JUDGE = "X"  # this has not been implemented as assuming there is a scoresheet - needs thought before doing
    JUDGING_MODEL_CHOICES = (
        (JUDGING_MODEL_SELF_ASSESSED, 'Self Assessed'),
        (JUDGING_MODEL_PREDEFINED, 'One or More Judges - Everyone judges all entries'),
        (JUDGING_MODEL_1OFMANY, 'One of Many Judges - Each entry judged by one judge from a selection'),
        (JUDGING_MODEL_MANY_OF_MANY, 'Any judge can choose to judge - Used for Training'),

    )
    DEFAULT_JUDGING_MODEL = "O"  # note that judging model for competition comes from competition type setting

    SCORING_MODEL_JUDGE_THEN_SCORE = "JT"
    SCORING_MODEL_JUDGE_AND_SCORE = "JA"
    SCORING_MODEL_SCORE_ONLY = "S"
    SCORING_MODEL_EXTERNAL_FEED = "E"
    SCORING_MODEL_CHOICES = (
        (SCORING_MODEL_JUDGE_THEN_SCORE, 'Judge then Score'),
        (SCORING_MODEL_JUDGE_AND_SCORE, 'Judge and Score'),
        (SCORING_MODEL_SCORE_ONLY, 'Score Only'),
        (SCORING_MODEL_EXTERNAL_FEED, 'External Feed'),
    )
    DEFAULT_SCORING_MODEL = SCORING_MODEL_JUDGE_THEN_SCORE


    SCHEDULING_MODEL_INDIVIDAULLY = "1"
    SCHEDULING_MODEL_ALL_AT_ONCE = "A"
    SCHEDULING_MODEL_NOT_SCHEDULED = "X"
    SCHEDULING_MODEL_CHOICES = (
        (SCHEDULING_MODEL_INDIVIDAULLY, 'Individually - eg. dressage'),
        (SCHEDULING_MODEL_ALL_AT_ONCE, 'All at once'),
        (SCHEDULING_MODEL_NOT_SCHEDULED, 'Not scheduled'),
    )
    DEFAULT_SCHEDULING_MODEL = "1"

    CALC_NONE = "-"
    CALC_DRESSAGE_POINT5 = "S"
    CALC_DRESSAGE_POINT1 = "G"
    CALC_SJ_SUMMARY = "JS"
    CALC_SJ_TIME_MANUAL = "JTM"

    CALC_CHOICES = (
        (CALC_NONE, "None"),
        (CALC_DRESSAGE_POINT5, "Dressage Standard (0-10/0.5)"), # 0 to 10 in whole numbers or steps of 0.5
        (CALC_DRESSAGE_POINT1, "Dressage Generic (0-10/.1)"),  # 0 to 10 in steps of .1
        (CALC_SJ_SUMMARY, "SJ Faults and Time by Round"),
        (CALC_SJ_TIME_MANUAL, "SJ Manual Timing"),
    )

    CALC_CHOICES_D = (
        (CALC_NONE, "None"),
        (CALC_DRESSAGE_POINT5, "Dressage Standard (0-10/0.5)"), # 0 to 10 in whole numbers or steps of 0.5
        (CALC_DRESSAGE_POINT1, "Dressage Generic (0-10/.1)"),  # 0 to 10 in steps of .1
    )

    CALC_CHOICES_J = (
        (CALC_NONE, "None"),
        (CALC_SJ_SUMMARY, "SJ Faults and Time by Round"),
        (CALC_SJ_TIME_MANUAL, "SJ Manual Timing"),
    )

    CALC_CHOICE_DEFAULT = CALC_DRESSAGE_POINT5

    SCORING_LEVEL_DETAIL = 'detail'
    SCORING_LEVEL_RESULT = 'score'
    SCORING_LEVEL_PLACING = 'placing'
    SCORING_LEVEL_CHOICES = (
    (SCORING_LEVEL_DETAIL, "Detail"),
    (SCORING_LEVEL_RESULT, "Score"),
    (SCORING_LEVEL_PLACING, "Placing"),
    )
    SCORING_LEVEL_DEFAULT = SCORING_LEVEL_DETAIL




def get_score_display4discipline(results_model, score, tiebreak=None, placing=None, mark_details={}, num_dp=2, scoring_level=None):
        """
        Create some text for displaying scores/results that are appropriate for this discipline and the scoring level set for the competition

        The text that will be output, e.g. "76.32%" or "C (.42)"

        For jumping, the agreed display format is:

        - Single round:
            - Clear: "C" or "C (43.21)" if a time is stored in tiebreak.
            - Faults: "4" or "4 (43.21)".
        - If you later add r1_faults / jo_faults, this method can show:
            - "0/0 (38.91)"   -> R1 clear, JO clear
            - "0/4 (39.44)"   -> R1 clear, 4 faults in JO
            - "4/– (78.11)"   -> 4 faults R1, no JO
        """

        if score == None:
            return ""

        if scoring_level == CompetitionTypeParams.SCORING_LEVEL_PLACING:
            return ordinal(placing)


        # --- Dressage: percentage ---------------------------------------------
        if results_model == CompetitionTypeParams.RESULTS_MODEL_DRESSAGE:
            return f"{score:.{num_dp}f}%"

        # --- Jumping: faults + optional time ----------------------------------
        elif results_model == CompetitionTypeParams.RESULTS_MODEL_JUMPING:
            # If you later add these fields, prefer them for the full format
            # r1_faults = mark_details.get("r1_faults", None)
            # jo_faults = mark_details.get("jo_faults", None)
            # time_str = str(tiebreak) if tiebreak not in (None, "") else ""
            #
            # # Case 1: we have explicit round faults (future-proof)
            # if r1_faults is not None and jo_faults is not None:
            #     if jo_faults in ("", None, "-"):
            #         # Single round / no jump-off
            #         if r1_faults == 0:
            #             pretty = "C"
            #         else:
            #             pretty = str(r1_faults)
            #     else:
            #         # Full R1/JO format
            #         pretty = f"{r1_faults}/{jo_faults}"
            #
            #     if time_str:
            #         pretty += f" ({time_str})"
            #     return pretty

            # Case 2: legacy/simple format using `score` as total faults
            faults = float(score or 0)
            time_str = str(tiebreak) if tiebreak not in (None, "") else ""

            if faults == 0.0:
                pretty = "C"
            else:
                # Show faults as an integer; no weird "score>99" encoding
                pretty = f"{faults:.{num_dp}f}"

            if time_str > "":
                pretty += f" ({time_str})"

            return pretty

        # --- Generic with tiebreak --------------------------------------------
        elif results_model == CompetitionTypeParams.RESULTS_MODEL_GENERIC_TIEBREAK:
            if tiebreak:
                return f"{score} ({tiebreak})"
            return f"{score}"

        # --- Generic numeric score only ---------------------------------------
        elif results_model == CompetitionTypeParams.RESULTS_MODEL_GENERIC_SCORE:
            return f"{score}"

        # --- Placing only ------------------------------------------------------
        elif results_model == CompetitionTypeParams.RESULTS_MODEL_PLACING_ONLY:
            return ordinal(placing)

        # --- Fallback: just show raw score ------------------------------------
        else:
            return f"{score}"


def get_score_sort4discipline(results_model, placing_model, score, tiebreak,placing=0, num_dp=2, withdrawn=False, withdrawn_type='' ) -> float:
        """
        Create a float value that can be used for sorting scores with *winner first*
        when sorted in ascending order.

        - Uses competition_type.placing_model:
            HH = score high,  tiebreak high  (higher is better)
            LH = score low,   tiebreak high
            HL = score high,  tiebreak low
            LL = score low,   tiebreak low   (e.g. SJ)

        - Withdrawn / eliminated etc. are always sorted at the end, but still ordered
          by their faults/time and withdrawn_type.

        - Does NOT include section in the key, so section only affects final placing,
          not raw score ordering.
        """



        # Handle "no placings" explicitly
        if placing_model == "-":
            return 0.0

        # placing_model is two letters: score-dir, tiebreak-dir
        # 'H' = higher is better, 'L' = lower is better
        score_dir = placing_model[0]
        tb_dir    = placing_model[1]

        # Base numeric values
        score    = float(score or 0)
        tiebreak = float(tiebreak or 0)

        # Special case: placing-only competitions
        if results_model == CompetitionTypeParams.RESULTS_MODEL_PLACING_ONLY:
            # Smaller placing number is always better - note that even if we are doing placing only, the placing is put in the score field
            score    = float(score or 0)
            tiebreak = 0.0
            score_dir = "L"
            tb_dir    = "L"

        # --- Map to a space where "smaller is better" for both components ---

        if score_dir == "H":
            eff_score = -score   # invert so higher score → smaller (better)
        else:
            eff_score = score    # lower is better already

        if tb_dir == "H":
            eff_tb = -tiebreak   # invert so higher tiebreak → smaller (better)
        else:
            eff_tb = tiebreak    # lower is better already

        # Combine score + tiebreak into a single float.
        # Scale tiebreak down so it only affects ordering within equal scores.

        scale = 10 ** (num_dp + 2)   # e.g. 10_000 for 2 dp

        combined = eff_score + eff_tb / scale
        # keep a few extra decimal places beyond num_dp
        combined = round(combined, num_dp + 4)

        # --- Push withdrawn / eliminated etc. to the end ---
        withdrawn_flag = 1 if withdrawn else 0

        # Optional: preserve a sensible order within the withdrawn block
        wt_index = 0
        if withdrawn_flag:
            order = ["NOS", "WD", "RET", "EL"]  # whatever order you prefer
            wt = (withdrawn_type or "").upper()
            wt_index = order.index(wt) if wt in order else len(order)

        # BIG must be much larger than any realistic score/time
        BIG = 1_000_000_000.0

        # Layout of the key:
        #  - normal results:        0           + combined
        #  - withdrawn results:     BIG         + wt_index * 1_000_000 + combined
        sortval = withdrawn_flag * BIG + wt_index * 1_000_000.0 + combined
        # final tidy: again round to avoid float noise
        sortval = round(sortval, num_dp + 4)
        return float(sortval)



def get_model_roles():
    path = getattr(settings, "MODEL_ROLES_PATH", None)
    if path is None:
        return None  # or raise ImproperlyConfigured here
    return import_string(path)

def get_disciplines():
    path = getattr(settings, "DISCIPLINES_PATH", None)
    if path is None:
        return None  # or raise ImproperlyConfigured here
    return import_string(path)

def get_competitiontype_params():
    path = getattr(settings, "COMPETITIONTYPE_PATH", None)
    if path is None:
        return None  # or raise ImproperlyConfigured here
    return import_string(path)
