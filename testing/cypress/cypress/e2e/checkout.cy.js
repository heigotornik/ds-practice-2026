describe("Checkout Flow", () => {
  beforeEach(() => {
    cy.visit("/");
  });

  function fillValidForm() {
    cy.get('input[name="name"]').clear().type("Paul");
    cy.get('input[name="contact"]').clear().type("paul@test.com");

    cy.get('input[name="creditCard"]')
      .clear()
      .type("4111111111111111");

    cy.get('input[name="expirationDate"]')
      .clear()
      .type("12/25");

    cy.get('input[name="cvv"]')
      .clear()
      .type("123");

    cy.get('textarea[name="userComment"]')
      .clear()
      .type("Test order");

    cy.get('input[name="billingStreet"]')
      .clear()
      .type("Street");

    cy.get('input[name="billingCity"]')
      .clear()
      .type("Tallinn");

    cy.get('input[name="billingState"]')
      .clear()
      .type("Harjumaa");

    cy.get('input[name="billingZip"]')
      .clear()
      .type("12345");

    cy.get('input[name="billingCountry"]')
      .clear()
      .type("Estonia");

    cy.get('select[name="shippingMethod"]')
      .select("Standard");

    cy.get('input[name="terms"]').check();
  }

  it("creates successful order", () => {
    fillValidForm();

    cy.get("form").submit();

    cy.contains("Order status:");
    cy.contains("Order Approved");
    cy.contains("Order ID:");
  });

  it("rejects fraudulent order", () => {
    fillValidForm();

    cy.get('input[name="creditCard"]')
      .clear()
      .type("9999");

    cy.get("form").submit();

    cy.contains("FAILED");
  });

  it("handles multiple non-conflicting orders", () => {
    const requests = [];

    for (let i = 0; i < 5; i++) {
      requests.push(
        fetch("http://localhost:8081/checkout", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            user: {
              name: `User${i}`,
              contact: `user${i}@test.com`,
            },
            creditCard: {
              number: "4111111111111111",
              expirationDate: "12/25",
              cvv: "123",
            },
            userComment: "Load test",
            items: [
              {
                name: `Book ${i}`,
                quantity: 1,
              },
            ],
            billingAddress: {
              street: "Street",
              city: "Tallinn",
              state: "Harjumaa",
              zip: "12345",
              country: "Estonia",
            },
            shippingMethod: "Standard",
            giftWrapping: false,
            termsAccepted: true,
          }),
        }).then((r) => r.json())
      );
    }

    cy.wrap(Promise.all(requests)).then((responses) => {
      responses.forEach((response) => {
        expect(response.status).to.eq("Order Approved");
      });
    });
  });

  it("handles mixed valid and invalid orders", () => {
    const orders = [
      {
        card: "4111111111111111",
        expected: "Order Approved",
      },
      {
        card: "9999",
        expected: "FAILED",
      },
      {
        card: "4111111111111111",
        expected: "Order Approved",
      },
    ];

    const requests = orders.map((order) =>
      fetch("http://localhost:8081/checkout", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          user: {
            name: "Paul",
            contact: "paul@test.com",
          },
          creditCard: {
            number: order.card,
            expirationDate: "12/25",
            cvv: "123",
          },
          userComment: "Mixed test",
          items: [
            {
              name: "Book A",
              quantity: 1,
            },
          ],
          billingAddress: {
            street: "Street",
            city: "Tallinn",
            state: "Harjumaa",
            zip: "12345",
            country: "Estonia",
          },
          shippingMethod: "Standard",
          giftWrapping: false,
          termsAccepted: true,
        }),
      }).then(async (r) => ({
        statusCode: r.status,
        body: await r.json(),
        expected: order.expected,
      }))
    );

    cy.wrap(Promise.all(requests)).then((responses) => {
      responses.forEach((response) => {
        expect(response.body.status).to.eq(response.expected);
      });
    });
  });

  it("handles conflicting orders", { timeout: 10000 }, () => {
    const payload = {
      user: {
        name: "Paul",
        contact: "paul@test.com",
      },
      creditCard: {
        number: "4111111111111111",
        expirationDate: "12/25",
        cvv: "123",
      },
      userComment: "Conflict test",
      items: [
        {
          name: "Some Book",
          quantity: 500,
        },
      ],
      billingAddress: {
        street: "Street",
        city: "Tallinn",
        state: "Harjumaa",
        zip: "12345",
        country: "Estonia",
      },
      shippingMethod: "Standard",
      giftWrapping: false,
      termsAccepted: true,
    };

    const requests = [
      fetch("http://localhost:8081/checkout", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      }).then(async (r) => ({
        statusCode: r.status,
        body: await r.json(),
      })),

      fetch("http://localhost:8081/checkout", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      }).then(async (r) => ({
        statusCode: r.status,
        body: await r.json(),
      })),
    ];

    cy.wrap(Promise.all(requests)).then((responses) => {
      console.log("Conflict responses:", responses);

      cy.log(JSON.stringify(responses, null, 2));

      const approved = responses.filter(
        (r) => r.body.status === "Order Approved"
      );

      const failed = responses.filter(
        (r) => r.body.status === "FAILED"
      );

      expect(approved.length).to.eq(2);
      expect(failed.length).to.eq(0);
    });
  });
});