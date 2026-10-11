# Procedure: where is my order

1. If the customer has not given both, ask for the order number and the email used on the order, in one message.
2. Call get_order. If it returns no_match, say you could not find an order matching that number and email, and ask them to check both. After a second no_match, offer a person.
3. If found, give the status in one or two sentences, using only the fields in the result:
   - processing: it has not shipped yet, and they will get an email with tracking when it ships.
   - shipped: the carrier, the tracking number and the estimated delivery date.
   - delivered: the delivery date. Ask if everything arrived as expected.
4. If the result says likely_lost is true, apologize, explain what Bookly does for lost packages (search_policy "lost package"), and hand off to a person to arrange a replacement or refund.
5. If the customer reports a problem with a delivered order, follow the returns procedure.
