"""
Testing the Comments in Python
"""

a="TechArkit"
b="Python"
string_c="TechArkit python training"

print(string_c.count("i"))

## Replacement String
y=string_c.replace("training","course")
print(y)

#Array/List
a=[10,20,30,40,50]
print(a)

a.insert(2,80)
print(a)

b=[1,"i","hello",20]
print(b)

print(b[2],b[1])
print(b.index(1))

print("hi"+' '+b[2]+' '+"How Are You")
print("the position of hello in variable b is "+str(b.index("hello")))

#Tuple - Once created not be modified
a=(1,2,3,7,3,5)
print(a.count(1))


#Dictionary {}
dict1={1:"Hi",2:"Hello",3:"Welcome"}
print(dict1.get(0))
print(dict1.get("Welcome"))
print(dict1.keys())
print(dict1.values())
