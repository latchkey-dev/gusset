class Svc:
    def outer(self):
        return self.inner()
    def inner(self):
        return 1
