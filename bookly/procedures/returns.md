# Procedure: returns and refunds

1. Understand what went wrong. If the customer is vague ("my order is messed up", "there's a problem"), ask one question:
   "Sorry about that. What happened?" and offer [[options: It arrived damaged | I got the wrong book | It hasn't arrived | I just want to return it]]
   If it has not arrived, follow the order status procedure instead.
2. Verify the order: order number and email, with get_order.
3. Work out which books. If the order has one book, that is the one. If it has several and the customer has not said which, call check_return_eligibility with an empty item_ids list. It returns needs_input with the books; ask which ones, and offer them as options.
4. Work out the reason from the customer's own words: damaged, wrong_item or changed_mind (see rule 4). If you cannot tell, ask.
5. Call check_return_eligibility with the order, the books and the reason. Then act on the decision:
   - refund_no_return or return_for_refund: summarize the outcome in a sentence or two, and ask the customer to review and confirm on the card. Wait for their answer.
   - ineligible: explain the reason plainly (the result says why), and offer a person.
   - needs_human: explain that refunds of this size are reviewed by a member of the team, call handoff_to_human with a summary, and share what happens next.
   - needs_input: ask the question for the missing field.
6. When FACTS SO FAR says the customer confirmed, call create_return with the quote_id. Then tell them it is done, with the return and refund references, and the label link if there is one.
7. If the customer declines, do not create anything. Ask whether they want something else or a person.
