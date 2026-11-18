Concepts
========

How Syndesi is built, and why. Nothing here is needed to use it, but everything here
helps to understand what it does.

.. grid:: 1 1 3 3
   :gutter: 3

   .. grid-item-card:: Adapters, protocols, drivers
      :link: layers
      :link-type: doc

      The three layers, what each one is responsible for, and how they stack.

   .. grid-item-card:: Frames and timeouts
      :link: frames
      :link-type: doc

      From bytes on a wire to a complete answer: fragments, stop conditions, buffers.

   .. grid-item-card:: The engine
      :link: engine
      :link-type: doc

      One background thread for every adapter, and why sync and async behave the same.
