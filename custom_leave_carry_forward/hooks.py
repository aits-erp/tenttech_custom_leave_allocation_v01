app_name = "custom_leave_carry_forward"
app_title = "custom_leave_carry_forward"
app_publisher = "Sukku"
app_description = "Custom Casual Leave carry forward functionality for HRMS"
app_email = "sukeshanee@gmail.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "custom_leave_carry_forward",
# 		"logo": "/assets/custom_leave_carry_forward/logo.png",
# 		"title": "custom_leave_carry_forward",
# 		"route": "/custom_leave_carry_forward",
# 		"has_permission": "custom_leave_carry_forward.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/custom_leave_carry_forward/css/custom_leave_carry_forward.css"
# app_include_js = "/assets/custom_leave_carry_forward/js/custom_leave_carry_forward.js"

# include js, css files in header of web template
# web_include_css = "/assets/custom_leave_carry_forward/css/custom_leave_carry_forward.css"
# web_include_js = "/assets/custom_leave_carry_forward/js/custom_leave_carry_forward.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "custom_leave_carry_forward/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "custom_leave_carry_forward/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "custom_leave_carry_forward.utils.jinja_methods",
# 	"filters": "custom_leave_carry_forward.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "custom_leave_carry_forward.install.before_install"
# after_install = "custom_leave_carry_forward.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "custom_leave_carry_forward.uninstall.before_uninstall"
# after_uninstall = "custom_leave_carry_forward.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "custom_leave_carry_forward.utils.before_app_install"
# after_app_install = "custom_leave_carry_forward.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "custom_leave_carry_forward.utils.before_app_uninstall"
# after_app_uninstall = "custom_leave_carry_forward.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "custom_leave_carry_forward.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"custom_leave_carry_forward.tasks.all"
# 	],
# 	"daily": [
# 		"custom_leave_carry_forward.tasks.daily"
# 	],
# 	"hourly": [
# 		"custom_leave_carry_forward.tasks.hourly"
# 	],
# 	"weekly": [
# 		"custom_leave_carry_forward.tasks.weekly"
# 	],
# 	"monthly": [
# 		"custom_leave_carry_forward.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "custom_leave_carry_forward.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "custom_leave_carry_forward.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "custom_leave_carry_forward.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["custom_leave_carry_forward.utils.before_request"]
# after_request = ["custom_leave_carry_forward.utils.after_request"]

# Job Events
# ----------
# before_job = ["custom_leave_carry_forward.utils.before_job"]
# after_job = ["custom_leave_carry_forward.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"custom_leave_carry_forward.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

