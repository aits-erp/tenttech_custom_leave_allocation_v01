# import frappe

# from frappe.utils import flt, getdate, add_days

# from hrms.hr.doctype.leave_allocation.leave_allocation import (
#     LeaveAllocation,
#     get_previous_allocation,
#     get_unused_leaves,
#     create_leave_ledger_entry,
#     validate_carry_forward,
# )


# class CustomLeaveAllocation(LeaveAllocation):
    
#     @frappe.whitelist()
#     def set_total_leaves_allocated(self):
#         """
#         Custom carry-forward logic for Casual Leave.

#         Other Leave Types continue using standard HRMS behavior.
#         """

#         # Standard behavior for all non-Casual Leave Types
#         if self.leave_type != "Casual Leave":
#             return super().set_total_leaves_allocated()

#         # If carry-forward is not enabled on Leave Allocation,
#         # no previous balance should be added.
#         if not self.carry_forward:
#             self.unused_leaves = 0
#             self.total_leaves_allocated = flt(
#                 self.new_leaves_allocated,
#                 self.precision("total_leaves_allocated"),
#             )
#             return

#         # Leave Type must have Is Carry Forward enabled
#         is_carry_forward = frappe.db.get_value(
#             "Leave Type",
#             self.leave_type,
#             "is_carry_forward",
#         )

#         if not is_carry_forward:
#             self.unused_leaves = 0
#             self.total_leaves_allocated = flt(
#                 self.new_leaves_allocated,
#                 self.precision("total_leaves_allocated"),
#             )
#             return

#         # Validate standard HRMS carry-forward setting
#         validate_carry_forward(self.leave_type)

#         # Get the latest previous allocation.
#         # This can be January even if February has no allocation.
#         previous_allocation = get_previous_allocation(
#             self.from_date,
#             self.leave_type,
#             self.employee,
#         )

#         unused_leaves = 0

#         if previous_allocation:
#             unused_leaves = get_unused_leaves(
#                 self.employee,
#                 self.leave_type,
#                 previous_allocation.from_date,
#                 previous_allocation.to_date,
#             )

#         # Apply custom Leave Type carry-forward date rules
#         unused_leaves = self.apply_custom_carry_forward_rules(
#             unused_leaves
#         )

#         self.unused_leaves = flt(
#             unused_leaves,
#             self.precision("unused_leaves"),
#         )

#         self.total_leaves_allocated = flt(
#             self.unused_leaves + flt(self.new_leaves_allocated),
#             self.precision("total_leaves_allocated"),
#         )

#         # Keep standard maximum allocation protection
#         self.limit_carry_forward_based_on_max_allowed_leaves()

#         # Keep standard tracking on previous allocation
#         if self.carry_forward:
#             self.set_carry_forwarded_leaves_in_previous_allocation()

#         if (
#             not self.total_leaves_allocated
#             and not frappe.db.get_value(
#                 "Leave Type",
#                 self.leave_type,
#                 "is_earned_leave",
#             )
#             and not frappe.db.get_value(
#                 "Leave Type",
#                 self.leave_type,
#                 "is_compensatory",
#             )
#         ):
#             frappe.throw(
#                 f"Total leaves allocated is mandatory for Leave Type {self.leave_type}"
#             )

#     def apply_custom_carry_forward_rules(self, unused_leaves):
#         """
#         Apply the custom Carry Forward From Date / To Date /
#         Infinite Carry Forward settings.
#         """

#         if not unused_leaves:
#             return 0

#         from_date = frappe.db.get_value(
#             "Leave Type",
#             self.leave_type,
#             "custom_carry_forward_from_date",
#         )

#         to_date = frappe.db.get_value(
#             "Leave Type",
#             self.leave_type,
#             "custom_carry_forward_to_date",
#         )

#         infinite = frappe.db.get_value(
#             "Leave Type",
#             self.leave_type,
#             "custom_infinite_carry_forward",
#         )

#         allocation_date = getdate(self.from_date)

#         # If a From Date is configured, carry-forward starts from that date.
#         if from_date and allocation_date < getdate(from_date):
#             return 0

#         # If To Date is configured and infinite carry-forward is OFF,
#         # carry-forward is allowed only up to that date.
#         if to_date and not infinite:
#             if allocation_date > getdate(to_date):
#                 return 0

#         return flt(unused_leaves)

#     def create_leave_ledger_entry(self, submit=True):
#         """
#         Create ledger entries.

#         Casual Leave uses the custom carry-forward calculation.
#         Other Leave Types use standard HRMS behavior.
#         """

#         if self.leave_type != "Casual Leave":
#             return super().create_leave_ledger_entry(submit=submit)

#         if self.unused_leaves:
#             # Carry-forward ledger entry
#             args = dict(
#                 leaves=self.unused_leaves,
#                 from_date=self.from_date,
#                 to_date=self.to_date,
#                 is_carry_forward=1,
#             )

#             create_leave_ledger_entry(self, args, submit)

#         # Normal allocation ledger entry
#         args = dict(
#             leaves=self.new_leaves_allocated,
#             from_date=self.from_date,
#             to_date=self.to_date,
#             is_carry_forward=0,
#         )

#         create_leave_ledger_entry(self, args, submit)


import frappe

from frappe import _

from frappe.utils import flt, getdate, cint

from hrms.hr.doctype.leave_allocation.leave_allocation import (
    LeaveAllocation,
    get_previous_allocation,
    get_unused_leaves,
    create_leave_ledger_entry,
    validate_carry_forward,
)


class CustomLeaveAllocation(LeaveAllocation):

    # =============================================================
    # CALCULATE TOTAL LEAVES ALLOCATED
    # =============================================================

    @frappe.whitelist(methods=["POST"])
    def set_total_leaves_allocated(self):
        """
        Custom carry-forward calculation for ALL Leave Types.

        Custom carry-forward logic applies when:

        1. Leave Allocation:
           "Add unused leaves from previous allocations" = checked

        2. Leave Type:
           "Is Carry Forward" = checked

        Custom Leave Type settings:

        - custom_carry_forward_from_date
        - custom_carry_forward_to_date
        - custom_infinite_carry_forward

        IMPORTANT:

        This method is called from the browser whenever fields
        are changed.

        Therefore this method ONLY calculates:

        - Unused Leaves
        - Total Leaves Allocated

        It does NOT:

        - show mandatory validation popup
        - save the document
        - submit the document
        - update previous Leave Allocation

        Mandatory validation is handled separately in validate().
        """

        # =========================================================
        # 1. No Leave Type selected
        # =========================================================

        if not self.leave_type:

            self.unused_leaves = 0

            self.total_leaves_allocated = flt(
                self.new_leaves_allocated,
                self.precision("total_leaves_allocated"),
            )

            return


        # =========================================================
        # 2. Standard Leave Allocation Carry Forward checkbox
        # =========================================================
        #
        # Standard field:
        #
        # Add unused leaves from previous allocations
        #
        # This is the MASTER SWITCH.
        # =========================================================

        if not self.carry_forward:

            self.unused_leaves = 0

            self.total_leaves_allocated = flt(
                self.new_leaves_allocated,
                self.precision("total_leaves_allocated"),
            )

            # IMPORTANT:
            # Do NOT validate here.
            return


        # =========================================================
        # 3. Check Leave Type > Is Carry Forward
        # =========================================================

        is_carry_forward = cint(
            frappe.db.get_value(
                "Leave Type",
                self.leave_type,
                "is_carry_forward",
            )
        )


        if not is_carry_forward:

            self.unused_leaves = 0

            self.total_leaves_allocated = flt(
                self.new_leaves_allocated,
                self.precision("total_leaves_allocated"),
            )

            # IMPORTANT:
            # Do NOT validate here.
            return


        # =========================================================
        # 4. Validate standard HRMS carry-forward configuration
        # =========================================================

        validate_carry_forward(self.leave_type)


        # =========================================================
        # 5. Get previous Leave Allocation
        # =========================================================

        previous_allocation = None

        if self.employee and self.from_date:

            previous_allocation = get_previous_allocation(
                self.from_date,
                self.leave_type,
                self.employee,
            )


        # =========================================================
        # 6. Calculate unused leaves
        # =========================================================

        unused_leaves = 0

        if previous_allocation:

            unused_leaves = get_unused_leaves(
                self.employee,
                self.leave_type,
                previous_allocation.from_date,
                previous_allocation.to_date,
            )


        # =========================================================
        # 7. Apply custom Carry Forward rules
        # =========================================================

        unused_leaves = self.apply_custom_carry_forward_rules(
            unused_leaves
        )


        # =========================================================
        # 8. Set Unused Leaves
        # =========================================================

        self.unused_leaves = flt(
            unused_leaves,
            self.precision("unused_leaves"),
        )


        # =========================================================
        # 9. Calculate Total Leaves Allocated
        # =========================================================

        self.total_leaves_allocated = flt(
            self.unused_leaves + flt(self.new_leaves_allocated),
            self.precision("total_leaves_allocated"),
        )


        # =========================================================
        # 10. Apply standard maximum carry-forward limit
        # =========================================================

        self.limit_carry_forward_based_on_max_allowed_leaves()


        # =========================================================
        # IMPORTANT
        # =========================================================
        #
        # DO NOT call:
        #
        # self.set_carry_forwarded_leaves_in_previous_allocation()
        #
        # DO NOT call mandatory validation here.
        #
        # This method is called repeatedly by the browser.
        #
        # It must ONLY calculate values.
        # =========================================================

        return


    # =============================================================
    # CUSTOM CARRY FORWARD DATE RULES
    # =============================================================

    def apply_custom_carry_forward_rules(self, unused_leaves):
        """
        Apply custom Carry Forward rules:

        - Carry Forward From Date
        - Carry Forward To Date
        - Infinite Carry Forward

        These rules apply dynamically to ALL Leave Types
        where Is Carry Forward is enabled.
        """

        # ---------------------------------------------------------
        # No unused leaves
        # ---------------------------------------------------------

        if not unused_leaves:
            return 0


        # ---------------------------------------------------------
        # Get Carry Forward From Date
        # ---------------------------------------------------------

        from_date = frappe.db.get_value(
            "Leave Type",
            self.leave_type,
            "custom_carry_forward_from_date",
        )


        # ---------------------------------------------------------
        # Get Carry Forward To Date
        # ---------------------------------------------------------

        to_date = frappe.db.get_value(
            "Leave Type",
            self.leave_type,
            "custom_carry_forward_to_date",
        )


        # ---------------------------------------------------------
        # Get Infinite Carry Forward
        # ---------------------------------------------------------

        infinite = cint(
            frappe.db.get_value(
                "Leave Type",
                self.leave_type,
                "custom_infinite_carry_forward",
            )
        )


        # ---------------------------------------------------------
        # If allocation date is not available
        # ---------------------------------------------------------

        if not self.from_date:
            return flt(unused_leaves)


        allocation_date = getdate(self.from_date)


        # =========================================================
        # Carry Forward From Date
        # =========================================================

        if from_date:

            if allocation_date < getdate(from_date):
                return 0


        # =========================================================
        # Carry Forward To Date
        # =========================================================
        #
        # Infinite Carry Forward = OFF
        #     -> To Date applies
        #
        # Infinite Carry Forward = ON
        #     -> To Date is ignored
        # =========================================================

        if to_date and not infinite:

            if allocation_date > getdate(to_date):
                return 0


        return flt(unused_leaves)


    # =============================================================
    # STANDARD HRMS VALIDATION
    # =============================================================

    def validate(self):
        """
        Standard HRMS validation during Save / Submit.

        IMPORTANT:

        set_total_leaves_allocated() is overridden because we need
        custom browser-side carry-forward calculation.

        Therefore the original HRMS mandatory validation from
        set_total_leaves_allocated() must be performed here,
        during document validation only.

        This prevents the mandatory popup from appearing when
        Employee, Leave Type, From Date, To Date, etc. are changed.
        """

        # =========================================================
        # 1. Run normal HRMS Leave Allocation validation
        # =========================================================

        super().validate()


        # =========================================================
        # 2. Preserve standard carry-forward tracking
        # =========================================================
        #
        # The original HRMS set_total_leaves_allocated() does this
        # before the mandatory total validation.
        #
        # We intentionally do it here instead of during browser
        # calculation to avoid the Record Changed / Deadlock error.
        # =========================================================

        if self.carry_forward:

            self.set_carry_forwarded_leaves_in_previous_allocation()


        # =========================================================
        # 3. Preserve standard HRMS over-allocation validation
        # =========================================================
        #
        # In your installed HRMS version, this method checks whether
        # total allocated leaves exceed the allocation period.
        # =========================================================

        LeaveAllocation.validate_total_leaves_allocated(self)


        # =========================================================
        # 4. ORIGINAL HRMS MANDATORY VALIDATION
        # =========================================================
        #
        # This is the exact mandatory validation from the
        # HRMS version installed on your system.
        #
        # Standard HRMS has this inside its
        # set_total_leaves_allocated().
        #
        # We move it here because our set_total_leaves_allocated()
        # is also called by browser field-change events.
        # =========================================================

        if (
            not self.total_leaves_allocated
            and not frappe.db.get_value(
                "Leave Type",
                self.leave_type,
                "is_earned_leave",
            )
            and not frappe.db.get_value(
                "Leave Type",
                self.leave_type,
                "is_compensatory",
            )
        ):

            frappe.throw(
                _(
                    "Total leaves allocated is mandatory for Leave Type {0}"
                ).format(self.leave_type)
            )


    # =============================================================
    # CREATE LEAVE LEDGER ENTRY
    # =============================================================

    def create_leave_ledger_entry(self, submit=True):
        """
        Create Leave Ledger entries.

        Carry-forward leaves:
            is_carry_forward = 1

        New allocation leaves:
            is_carry_forward = 0
        """

        # =========================================================
        # 1. Carry-forward ledger entry
        # =========================================================

        if self.unused_leaves:

            args = dict(
                leaves=self.unused_leaves,
                from_date=self.from_date,
                to_date=self.to_date,
                is_carry_forward=1,
            )

            create_leave_ledger_entry(
                self,
                args,
                submit,
            )


        # =========================================================
        # 2. Normal allocation ledger entry
        # =========================================================

        args = dict(
            leaves=self.new_leaves_allocated,
            from_date=self.from_date,
            to_date=self.to_date,
            is_carry_forward=0,
        )

        create_leave_ledger_entry(
            self,
            args,
            submit,
        )