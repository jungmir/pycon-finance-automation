from .base import BaseHandler
from ..clients.dooray import (
    DoorayClient,
    DOORAY_STATUS_PAYMENT_PENDING,
    DOORAY_STATUS_REJECTED,
)


class Step5PaymentHandler(BaseHandler):
    name = "step5_payment"
    from_state = "COPIED_TO_PYCON"
    to_state = "PAYMENT_PENDING"

    def __init__(
        self,
        store,
        notifier,
        dooray: DoorayClient,
        pajunwi_project_id: str,
        pycon_project_id: str,
    ):
        super().__init__(store, notifier)
        self.dooray = dooray
        self.pajunwi_project_id = pajunwi_project_id
        self.pycon_project_id = pycon_project_id

    def execute(self, task: dict):
        pajunwi_task_id = task["pajunwi_task_id"]
        pycon_task_id = task["pycon_task_id"]

        pycon_task = self.dooray.get_task(self.pycon_project_id, pycon_task_id)
        dooray_status = pycon_task.get("workflowClass")

        if dooray_status == DOORAY_STATUS_REJECTED:
            # REJECTED uses a special bypass: execute() sets state directly and returns None
            # so BaseHandler does NOT apply the normal COPIED_TO_PYCON→PAYMENT_PENDING transition.
            # This is safe because:
            #   1. BaseHandler returns immediately on None (no retry)
            #   2. StateEngine only dispatches handlers for tasks in from_state (COPIED_TO_PYCON)
            #      so a REJECTED task is never picked up again
            self.store.upsert_task(pajunwi_task_id, "REJECTED")
            self.store.log_transition(
                pajunwi_task_id, "COPIED_TO_PYCON", "REJECTED", self.name, True
            )
            self.notifier.task_rejected(pycon_task_id)
            return None

        if dooray_status != DOORAY_STATUS_PAYMENT_PENDING:
            return None  # still in review, not ready

        # Check-before-act on pajunwi side
        pajunwi_task = self.dooray.get_task(self.pajunwi_project_id, pajunwi_task_id)
        if pajunwi_task.get("workflowClass") != DOORAY_STATUS_PAYMENT_PENDING:
            self.dooray.update_task_status(
                self.pajunwi_project_id, pajunwi_task_id, DOORAY_STATUS_PAYMENT_PENDING
            )

        return True
