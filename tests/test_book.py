from random import Random
import unittest

from aegis.book import Order, OrderBook


class BookTests(unittest.TestCase):
    def setUp(self):
        self.book = OrderBook("X")

    def o(self, key, side, price, qty, owner="maker"):
        return Order(key, "X", owner, side, price, qty)

    def test_price_then_time_priority_and_partial_fill(self):
        for order in [self.o("expensive",-1,105,4), self.o("first",-1,100,3), self.o("second",-1,100,3)]:
            self.book.submit(order)
        fills, reason = self.book.submit(self.o("take",1,105,5,"taker"), immediate_or_cancel=True)
        self.assertIsNone(reason)
        self.assertEqual([(f.maker_id,f.quantity,f.ticks) for f in fills], [("first",3,100),("second",2,100)])
        self.assertEqual(self.book.orders["second"].remaining,1)
        self.assertEqual(self.book.orders["expensive"].remaining,4)

    def test_bid_price_priority(self):
        self.book.submit(self.o("low",1,95,1))
        self.book.submit(self.o("high",1,100,1))
        fills,_ = self.book.submit(self.o("sell",-1,95,1,"taker"), immediate_or_cancel=True)
        self.assertEqual(fills[0].maker_id,"high")

    def test_post_only_cross_does_not_trade(self):
        self.book.submit(self.o("ask",-1,100,2))
        fills,reason = self.book.submit(self.o("bid",1,100,1,"taker"),post_only=True)
        self.assertEqual(reason,"POST_ONLY_CROSS")
        self.assertEqual(fills,[])
        self.assertEqual(self.book.orders["ask"].remaining,2)
        self.assertNotIn("bid",self.book.orders)

    def test_cancel_and_duplicate_id(self):
        self.book.submit(self.o("one",1,100,2))
        self.assertIsNotNone(self.book.cancel("one"))
        self.assertIsNone(self.book.cancel("one"))
        self.assertIsNone(self.book.best(1))
        with self.assertRaises(ValueError):
            self.book.submit(self.o("one",1,100,2))

    def test_ioc_never_rests(self):
        self.book.submit(self.o("take",1,100,2,"taker"),immediate_or_cancel=True)
        self.assertEqual(self.book.orders,{})

    def test_self_match_prevention(self):
        self.book.submit(self.o("ask",-1,100,1,"same"))
        fills, reason = self.book.submit(self.o("buy",1,100,1,"same"))
        self.assertEqual(reason,"SELF_MATCH_PREVENTED")
        self.assertEqual(fills,[])
        self.assertNotIn("buy",self.book.orders)

    def test_randomized_matching_conserves_quantity_and_uncrossed_book(self):
        rng=Random(19)
        submitted=filled=0
        for i in range(1000):
            side=rng.choice([-1,1]);quantity=rng.randint(1,7)
            order=self.o(str(i),side,rng.randint(95,105),quantity,owner=str(i))
            submitted+=quantity
            matches,_=self.book.submit(order)
            filled+=sum(match.quantity for match in matches)
            bid,ask=self.book.best(1),self.book.best(-1)
            if bid is not None and ask is not None:
                self.assertLess(bid,ask)
            self.assertEqual(submitted,2*filled+sum(x.remaining for x in self.book.orders.values()))

    def test_invalid_tick_and_quantity(self):
        for order in [self.o("a",0,100,1),self.o("b",1,0,1),self.o("c",1,100,0),self.o("d",1,1.5,1)]:
            with self.assertRaises(ValueError):
                self.book.submit(order)
