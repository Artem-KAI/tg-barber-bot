"""All user-facing English string constants (clean typography, no stickers/emojis)."""
from __future__ import annotations

__all__ = [
    "MSG",
    "BTN",
    "WEEKDAY_NAMES",
    "WEEKDAY_SHORT",
    "TIME_SLOTS",
    "MAPS_URL",
    "SHOP_NAME",
    "SHOP_ADDRESS",
    "SHOP_HOURS",
]

# ── Shop info ────────────────────────────────────────────────────────────────
SHOP_NAME = "The Iron Throne Barbershop"
SHOP_ADDRESS = "347 W 42nd St, New York, NY 10036"
SHOP_HOURS = "Mon–Sat: 9:00 AM – 8:00 PM"
MAPS_URL = "https://www.google.com/maps/search/?api=1&query=347+W+42nd+St+New+York+NY+10036"

# ── Weekday labels (Monday=0) ─────────────────────────────────────────────────
WEEKDAY_NAMES: list[str] = [
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"
]

WEEKDAY_SHORT: list[str] = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# ── Preset time slots ────────────────────────────────────────────────────────
TIME_SLOTS: list[str] = [
    "09:00", "10:00", "11:00", "12:00", "13:00",
    "14:00", "15:00", "16:00", "17:00", "18:00", "19:00",
]

# ── Button labels (clean text, no emojis) ────────────────────────────────────
BTN: dict[str, str] = {
    # Main menu
    "book": "Book an Appointment",
    "my_bookings": "My Bookings",
    "location": "Location & Map",
    "become_barber": "Become a Barber",
    "app_status": "Application Status",
    "barber_studio": "Barber Studio",
    "admin_panel": "Admin Panel",
    "cancel": "Cancel",
    # Navigation
    "back": "Back",
    "done": "Done",
    "confirm": "Confirm",
    "yes": "Yes",
    "no": "No",
    # Booking actions (client)
    "edit_name": "Edit Name",
    "edit_phone": "Edit Phone",
    "change_service": "Change Service",
    "change_barber": "Change Barber",
    "cancel_booking": "Cancel Booking",
    # Booking actions (barber)
    "confirm_booking": "Confirm",
    "decline_booking": "Decline",
    "change_service_barber": "Change Service",
    "change_price_barber": "Change Price",
    "mark_done": "Mark as Done",
    # Barber studio
    "incoming_bookings": "Incoming Bookings",
    "my_profile": "My Profile",
    "edit_barber_name": "Edit Name",
    "edit_bio": "Edit Bio",
    "edit_segment": "Edit Segment",
    "service_prices": "Service Prices",
    "my_schedule": "My Schedule",
    "days_off": "Days Off",
    "leave_barbershop": "Leave Barbershop",
    "yes_leave": "Yes, leave",
    # Admin panel
    "pending_apps": "Pending Barber Applications",
    "all_barbers": "All Barbers",
    "all_bookings": "All Bookings",
    "studio_prices": "Studio Service Prices",
    "admin_approve": "Approve",
    "admin_reject": "Reject",
    "admin_set_rating": "Set Rating",
    "admin_remove": "Remove Barber",
    "admin_remove_yes": "Yes, remove",
    # Maps
    "open_maps": "Open in Google Maps",
    # Schedule
    "save_days": "Save Days",
    "save_slots": "Save Slots",
}

# ── Message templates (clean text, no emojis) ────────────────────────────────
MSG: dict[str, str] = {
    # General
    "welcome": (
        "Welcome to <b>{shop}</b>.\n\n"
        "We are a premium barbershop in New York City. "
        "Use the menu below to get started."
    ),
    "cancelled": "Action cancelled. Returning to the main menu.",
    "unknown": "Command not recognised. Please use the menu buttons below.",
    "error": "An error occurred. Please try again.",

    # Location
    "location": (
        "<b>{shop}</b>\n"
        "Address: {address}\n"
        "Hours: {hours}\n\n"
        "Click the button below to open the location in Google Maps."
    ),

    # Booking flow
    "book_name": "Please enter your <b>full name</b>:",
    "book_phone": "Please enter your <b>phone number</b> (e.g. +1-555-0100):",
    "book_service": "Choose a <b>service</b>:",
    "book_barber": "Choose your <b>barber</b>:",
    "book_date": "Choose an <b>available date</b>:",
    "book_slot": "Choose an <b>available time slot</b>:",
    "book_confirm": "Please review your booking details:",
    "book_ok": "Your booking has been submitted. We will notify you once it is confirmed.",
    "book_no_barbers": "No barbers are currently available. Please try again later.",
    "book_no_dates": "No available dates for this barber in the next 14 days.",
    "book_no_slots": "No available time slots for the selected date.",

    # My bookings
    "my_bookings_empty": "You have no bookings yet.",
    "my_bookings_list": "<b>Your Bookings</b> (tap one to manage):",

    # Client edit fields
    "enter_new_name": "Enter a new <b>name</b>:",
    "enter_new_phone": "Enter a new <b>phone number</b>:",
    "updated_ok": "Updated successfully.",
    "booking_cancelled_ok": "Booking cancelled.",

    # Become a barber
    "apply_name": "Enter your <b>barber name</b> (professional name or real name):",
    "apply_bio": "Write a short <b>bio</b> about yourself (skills, experience, style):",
    "apply_segment": (
        "Choose your <b>price segment</b>:\n\n"
        "• <b>budget</b> — affordable prices\n"
        "• <b>standard</b> — mid-range prices\n"
        "• <b>premium</b> — high-end experience"
    ),
    "apply_done": (
        "<b>Application submitted.</b>\n\n"
        "Our admin will review your application shortly. "
        "You can check your status from the main menu."
    ),
    "already_applied": "Your application is already under review.",
    "already_barber": "You are already a registered barber at our shop.",
    "app_pending": "<b>Application Status:</b> Under review. Please wait for admin approval.",
    "app_rejected": "<b>Application Status:</b> Your application was not approved.",
    "app_none": "You have not applied to become a barber.",

    # Barber cabinet
    "barber_studio": "<b>Barber Studio</b>\n\nWelcome back, <b>{name}</b>. Choose an option:",
    "barber_profile": "<b>Your Profile</b>\n\n{card}",
    "barber_enter_name": "Enter your new <b>barber name</b>:",
    "barber_enter_bio": "Enter your new <b>bio</b>:",
    "barber_enter_segment": "Enter your new <b>segment</b> (budget / standard / premium):",
    "barber_updated": "Profile updated.",
    "barber_enter_price": "Enter the new price for <b>{service}</b> (numbers only, e.g. 35):",
    "barber_price_updated": "Price updated.",
    "no_incoming": "No incoming bookings at the moment.",
    "incoming_list": "<b>Incoming Bookings</b> (tap one to manage):",

    # Schedule
    "schedule_days": (
        "<b>My Schedule — Work Days</b>\n\n"
        "Tap a day to toggle it on/off. Tap <b>Save Days</b> when done."
    ),
    "schedule_slots": (
        "<b>My Schedule — Time Slots</b>\n\n"
        "Tap a slot to toggle it on/off. Tap <b>Save Slots</b> when done."
    ),
    "schedule_saved": "Schedule saved successfully.",

    # Days off
    "days_off_pick": (
        "<b>Days Off Management</b>\n\n"
        "Tap a date to mark or unmark it as a day off. Tap <b>Done</b> when finished."
    ),
    "days_off_saved": "Days off updated successfully.",

    # Leave barbershop
    "leave_confirm": (
        "<b>Delete Barber Profile &amp; Leave?</b>\n\n"
        "Are you sure you want to delete your barber profile? "
        "Your profile, schedule, and time slots will be removed. "
        "You can apply again at any time."
    ),
    "leave_done": "Your barber profile has been removed. You can re-apply anytime from the menu.",
    "leave_cancelled": "Action cancelled. Your profile remains active.",

    # Admin panel
    "admin_panel": "<b>Admin Panel</b> — Choose an option:",
    "admin_no_pending": "No pending barber applications.",
    "admin_no_barbers": "No barbers registered yet.",
    "admin_no_bookings": "No bookings yet.",
    "admin_approve": "Approve",
    "admin_reject": "Reject",
    "admin_approved_ok": "Barber approved and notified.",
    "admin_rejected_ok": "Application rejected and applicant notified.",
    "admin_service_list": "<b>Studio Service Prices</b>\n\n{list}",
    "admin_enter_price": "Enter the new price for <b>{service}</b>:",
    "admin_price_updated": "Price for <b>{service}</b> updated to <b>${price}</b>.",
    "admin_enter_rating": "Enter the new <b>rating</b> for <b>{name}</b> (1–5, e.g. 4.8):",
    "admin_rating_updated": "Rating updated.",
    "admin_remove_confirm": (
        "Remove barber <b>{name}</b>?\n\n"
        "Their active bookings will be cancelled and the clients notified."
    ),
    "admin_removed_ok": "Barber removed.",
    "admin_cannot_remove_self": "The studio admin's own barber profile cannot be removed.",
    "notify_barber_removed": "Your barber profile was removed by the administrator.",

    # Notifications (sent to barber)
    "notify_barber_new_booking": "<b>New Booking Received:</b>\n\n{card}",
    "notify_barber_cancelled": "Booking #{id} has been cancelled by the client.",
    "notify_barber_approved": (
        "Your barber application has been approved. "
        "You can now access the Barber Studio from the main menu."
    ),
    "notify_barber_rejected": (
        "Your barber application was not approved."
    ),
    "notify_admin_left": "Barber <b>{name}</b> (ID: {id}) has left the barbershop.",
    "notify_client_confirmed": "Your booking #{id} has been confirmed by the barber.",
    "notify_client_declined": "Your booking #{id} has been declined by the barber.",
    "notify_client_done": "Your booking #{id} has been marked as completed. Thank you for your visit.",

    # Barber actions on booking
    "barber_enter_service": "Enter the new <b>service name</b> for this booking:",
    "barber_enter_price_booking": "Enter the new <b>price</b> for this booking (numbers only):",
    "notify_client_updated": "Your booking #{id} was updated by the barber:\n\n{card}",
    "notify_barber_updated": "<b>Booking updated by the client:</b>\n\n{card}",
    "notify_barber_reassigned": "Booking #{id} was moved to another barber by the client.",
    "notify_client_barber_left": (
        "Your booking #{id} was cancelled because the barber is no longer available. "
        "Please book again with another barber."
    ),

    # Validation / stale buttons
    "invalid_name": "Please send your name as text (2–64 characters):",
    "invalid_phone": "Please send a valid phone number (7–15 digits, e.g. +1-555-0100):",
    "invalid_text": "Please send this as a text message (up to {max} characters):",
    "invalid_price": "Invalid price. Please enter a positive number up to 10000:",
    "invalid_rating": "Invalid rating. Please enter a number from 1 to 5 (e.g. 4.8):",
    "use_buttons": "Please use the buttons above, or press Cancel.",
    "stale_button": "This menu is no longer active.",
    "booking_not_editable": "This booking can no longer be changed.",
    "slot_taken": "Sorry, this time was just taken. Please choose another slot:",
    "barber_unavailable": "This barber is not available at the booking's date and time.",
    "not_active_barber": "Your barber profile is not active.",
    "schedule_need_day": "Select at least one work day. Use Days Off for vacations.",
    "schedule_need_slot": "Select at least one time slot.",
    "days_off_has_bookings": (
        "You have {n} active booking(s) on this date. "
        "Decline them in Incoming Bookings first."
    ),
    "schedule_conflict": (
        "{n} upcoming booking(s) don't fit the new schedule (first: {first}). "
        "Decline them in Incoming Bookings first, or keep that day/slot."
    ),
    "notify_client_expired": (
        "Your booking request #{id} expired because the barber did not confirm it in time. "
        "Please book again."
    ),
    "barber_pick_service": "Choose the new <b>service</b> for this booking:",
}
