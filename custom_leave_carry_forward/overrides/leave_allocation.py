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

from frappe.utils import flt, getdate

from hrms.hr.doctype.leave_allocation.leave_allocation import (
    LeaveAllocation,
    get_previous_allocation,
    get_unused_leaves,
    create_leave_ledger_entry,
    validate_carry_forward,
)


class CustomLeaveAllocation(LeaveAllocation):

    @frappe.whitelist()
    def set_total_leaves_allocated(self):
        """
        Custom carry-forward calculation for Casual Leave.

        Other Leave Types continue using standard HRMS behavior.

        This method is used while the Leave Allocation form is being
        filled in the browser.

        IMPORTANT:
        This method only calculates unused leaves and total leaves.
        It must NOT update the previous Leave Allocation record here,
        because this method can be called multiple times while entering
        Employee, Leave Type, From Date, To Date, etc.
        """

        # ---------------------------------------------------------
        # 1. Non-Casual Leave Types
        # ---------------------------------------------------------
        # Keep standard HRMS behavior for all other Leave Types.
        if self.leave_type != "Casual Leave":
            return super().set_total_leaves_allocated()

        # ---------------------------------------------------------
        # 2. Leave Allocation Carry Forward checkbox
        # ---------------------------------------------------------
        # Standard field:
        # "Add unused leaves from previous allocations"
        #
        # This remains the master switch.
        if not self.carry_forward:
            self.unused_leaves = 0

            self.total_leaves_allocated = flt(
                self.new_leaves_allocated,
                self.precision("total_leaves_allocated"),
            )

            return

        # ---------------------------------------------------------
        # 3. Leave Type > Is Carry Forward
        # ---------------------------------------------------------
        # The standard Leave Type setting must also be enabled.
        is_carry_forward = frappe.db.get_value(
            "Leave Type",
            self.leave_type,
            "is_carry_forward",
        )

        if not is_carry_forward:
            self.unused_leaves = 0

            self.total_leaves_allocated = flt(
                self.new_leaves_allocated,
                self.precision("total_leaves_allocated"),
            )

            return

        # ---------------------------------------------------------
        # 4. Validate standard HRMS carry-forward configuration
        # ---------------------------------------------------------
        validate_carry_forward(self.leave_type)

        # ---------------------------------------------------------
        # 5. Find previous Leave Allocation
        # ---------------------------------------------------------
        # This uses the standard HRMS helper.
        #
        # Example:
        #
        # January:
        # 01-01-2026 -> 31-01-2026
        #
        # February:
        # No allocation
        #
        # March:
        # 01-03-2026 -> 31-03-2026
        #
        # The previous January allocation can therefore be used.
        previous_allocation = get_previous_allocation(
            self.from_date,
            self.leave_type,
            self.employee,
        )

        unused_leaves = 0

        if previous_allocation:
            unused_leaves = get_unused_leaves(
                self.employee,
                self.leave_type,
                previous_allocation.from_date,
                previous_allocation.to_date,
            )

        # ---------------------------------------------------------
        # 6. Apply custom Carry Forward date rules
        # ---------------------------------------------------------
        unused_leaves = self.apply_custom_carry_forward_rules(
            unused_leaves
        )

        # ---------------------------------------------------------
        # 7. Set Unused Leaves
        # ---------------------------------------------------------
        self.unused_leaves = flt(
            unused_leaves,
            self.precision("unused_leaves"),
        )

        # ---------------------------------------------------------
        # 8. Calculate Total Leaves Allocated
        # ---------------------------------------------------------
        #
        # Example:
        #
        # Previous unused leaves = 3
        # New leaves allocated   = 1.5
        #
        # Total = 4.5
        #
        self.total_leaves_allocated = flt(
            self.unused_leaves + flt(self.new_leaves_allocated),
            self.precision("total_leaves_allocated"),
        )

        # ---------------------------------------------------------
        # 9. Apply standard maximum carry-forward limit
        # ---------------------------------------------------------
        self.limit_carry_forward_based_on_max_allowed_leaves()

        # ---------------------------------------------------------
        # IMPORTANT
        # ---------------------------------------------------------
        #
        # DO NOT do this here:
        #
        # self.set_carry_forwarded_leaves_in_previous_allocation()
        #
        # That method performs a database update on the previous
        # Leave Allocation.
        #
        # This calculation method is called repeatedly from the
        # browser while the document is still being edited.
        #
        # Updating the previous record here can result in:
        #
        # QueryDeadlockError:
        # Record has changed since last read in table
        # 'tabLeave Allocation'
        #
        # Therefore, previous allocation tracking is NOT performed
        # during this calculation request.

        return


    def apply_custom_carry_forward_rules(self, unused_leaves):
        """
        Apply custom Leave Type carry-forward settings.

        Custom fields:

        custom_carry_forward_from_date
        custom_carry_forward_to_date
        custom_infinite_carry_forward
        """

        # Nothing to carry forward.
        if not unused_leaves:
            return 0

        # ---------------------------------------------------------
        # Get custom Carry Forward From Date
        # ---------------------------------------------------------
        from_date = frappe.db.get_value(
            "Leave Type",
            self.leave_type,
            "custom_carry_forward_from_date",
        )

        # ---------------------------------------------------------
        # Get custom Carry Forward To Date
        # ---------------------------------------------------------
        to_date = frappe.db.get_value(
            "Leave Type",
            self.leave_type,
            "custom_carry_forward_to_date",
        )

        # ---------------------------------------------------------
        # Get Infinite Carry Forward setting
        # ---------------------------------------------------------
        infinite = frappe.db.get_value(
            "Leave Type",
            self.leave_type,
            "custom_infinite_carry_forward",
        )

        allocation_date = getdate(self.from_date)

        # ---------------------------------------------------------
        # Carry Forward From Date
        # ---------------------------------------------------------
        #
        # Example:
        #
        # From Date = 01-01-2026
        #
        # An allocation before 01-01-2026 will not receive
        # carry-forward.
        #
        if from_date:
            if allocation_date < getdate(from_date):
                return 0

        # ---------------------------------------------------------
        # Carry Forward To Date
        # ---------------------------------------------------------
        #
        # If Infinite Carry Forward is OFF:
        # carry-forward stops after To Date.
        #
        # If Infinite Carry Forward is ON:
        # To Date is ignored.
        #
        if to_date and not infinite:
            if allocation_date > getdate(to_date):
                return 0

        return flt(unused_leaves)


    def create_leave_ledger_entry(self, submit=True):
        """
        Create Leave Ledger entries.

        Casual Leave uses the custom carry-forward calculation.

        Other Leave Types continue using standard HRMS behavior.
        """

        # ---------------------------------------------------------
        # 1. Non-Casual Leave Types
        # ---------------------------------------------------------
        if self.leave_type != "Casual Leave":
            return super().create_leave_ledger_entry(
                submit=submit
            )

        # ---------------------------------------------------------
        # 2. Carry-forward ledger entry
        # ---------------------------------------------------------
        #
        # If unused leaves were carried forward:
        #
        # is_carry_forward = 1
        #
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

        # ---------------------------------------------------------
        # 3. Normal new allocation ledger entry
        # ---------------------------------------------------------
        #
        # New leaves are stored separately:
        #
        # is_carry_forward = 0
        #
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